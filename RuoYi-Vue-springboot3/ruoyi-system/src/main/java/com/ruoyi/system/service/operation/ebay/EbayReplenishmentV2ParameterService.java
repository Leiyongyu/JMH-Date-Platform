package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayReplenishmentV2Parameter;
import com.ruoyi.system.mapper.operation.ebay.EbayReplenishmentV2ParameterMapper;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.DigestUtils;

/** 参数管理独立于现有预测/分级公式，后续计算通过稳定键读取。 */
@Service
public class EbayReplenishmentV2ParameterService
{
    public record Field(String key, String label, String type, String defaultValue,
                        BigDecimal min, BigDecimal max, int precision, boolean nullable) {}
    public record Row(String key, String label, String description, List<Field> fields) {}
    public record Module(String key, String label, List<Row> rows) {}
    public record Snapshot(String revision, List<Module> modules, Map<String, String> values) {}
    public record SaveRequest(String revision, Map<String, String> values) {}

    private static final String DEPLOY_MESSAGE = "参数配置尚未部署完整，请执行20260928_ebay_replenishment_v2_parameters.sql";
    private final EbayReplenishmentV2ParameterMapper mapper;
    private final List<Module> modules;
    private final Map<String, Field> fields = new LinkedHashMap<>();

    public EbayReplenishmentV2ParameterService(EbayReplenishmentV2ParameterMapper mapper)
    {
        this.mapper = mapper;
        try (var input = new ClassPathResource("ebay/replenishment-v2-parameters.json").getInputStream())
        {
            modules = new ObjectMapper().readValue(input, new TypeReference<List<Module>>() {});
            modules.forEach(module -> module.rows().forEach(row -> row.fields().forEach(field -> fields.put(field.key(), field))));
        }
        catch (IOException e)
        {
            throw new IllegalStateException("无法加载eBay补货参数目录", e);
        }
    }

    public Snapshot get()
    {
        return snapshot(read(false));
    }

    @Transactional(rollbackFor = Exception.class)
    public Snapshot save(SaveRequest request, String operator)
    {
        if (request == null || request.values() == null || !fields.keySet().equals(request.values().keySet()))
            throw new ServiceException("请提交完整参数，参数项不得缺失或增加");
        // 全部校验通过才写入，避免半份配置。
        Map<String, String> values = validate(request.values());
        List<EbayReplenishmentV2Parameter> stored = read(true);
        if (!Objects.equals(request.revision(), snapshot(stored).revision()))
            throw new ServiceException("参数已被其他用户修改，请重新打开弹窗后再保存");
        for (var row : stored)
        {
            String value = values.get(row.getParameterKey());
            if (Objects.equals(value, valueOf(row))) continue;
            Field field = fields.get(row.getParameterKey());
            row.setTextValue("grade".equals(field.type()) ? value : null);
            row.setNumericValue("grade".equals(field.type()) || value == null ? null : new BigDecimal(value));
            if (mapper.updateValue(row, operator) != 1)
                throw new ServiceException("参数保存冲突，请重新打开弹窗后再保存");
            row.setRevision(row.getRevision() + 1);
        }
        return snapshot(stored);
    }

    private List<EbayReplenishmentV2Parameter> read(boolean lock)
    {
        List<EbayReplenishmentV2Parameter> rows;
        try { rows = mapper.selectAll(lock); }
        catch (BadSqlGrammarException e)
        {
            if (e.getSQLException() != null && e.getSQLException().getErrorCode() == 1146)
                throw new ServiceException(DEPLOY_MESSAGE);
            throw e;
        }
        Set<String> keys = rows.stream().map(EbayReplenishmentV2Parameter::getParameterKey).collect(Collectors.toSet());
        if (rows.size() != fields.size() || !keys.equals(fields.keySet())) throw new ServiceException(DEPLOY_MESSAGE);
        return rows;
    }

    private Snapshot snapshot(List<EbayReplenishmentV2Parameter> rows)
    {
        Map<String, String> values = new LinkedHashMap<>();
        StringBuilder revision = new StringBuilder();
        rows.stream().sorted(java.util.Comparator.comparing(EbayReplenishmentV2Parameter::getParameterKey)).forEach(row -> {
            values.put(row.getParameterKey(), valueOf(row));
            revision.append(row.getParameterKey()).append(':').append(row.getRevision())
                    .append(':').append(valueOf(row)).append('\n');
        });
        return new Snapshot(DigestUtils.md5DigestAsHex(revision.toString().getBytes(StandardCharsets.UTF_8)), modules, values);
    }

    private String valueOf(EbayReplenishmentV2Parameter row)
    {
        return row.getTextValue() != null ? row.getTextValue() : decimalText(row.getNumericValue());
    }

    private String decimalText(BigDecimal value)
    {
        return value == null ? null : value.stripTrailingZeros().toPlainString();
    }

    private Map<String, String> validate(Map<String, String> submitted)
    {
        Map<String, String> result = new LinkedHashMap<>();
        for (Field field : fields.values())
        {
            String value = submitted.get(field.key());
            value = value == null ? null : value.trim();
            if (value == null || value.isEmpty())
            {
                if (!field.nullable()) throw new ServiceException(field.label() + "不能为空");
                result.put(field.key(), null);
                continue;
            }
            if ("grade".equals(field.type()))
            {
                if (!Set.of("S", "A", "B", "C", "D").contains(value)) throw new ServiceException("负毛利硬降档必须为S/A/B/C/D");
                result.put(field.key(), value);
                continue;
            }
            BigDecimal number;
            try { number = new BigDecimal(value); }
            catch (NumberFormatException e) { throw new ServiceException(field.label() + "必须为有效数字"); }
            if (number.compareTo(field.min()) < 0 || number.compareTo(field.max()) > 0
                    || number.stripTrailingZeros().scale() > field.precision())
                throw new ServiceException(field.label() + "须在" + field.min() + "至" + field.max()
                        + "之间，最多" + field.precision() + "位小数");
            result.put(field.key(), decimalText(number));
        }
        validateRelationships(result);
        return result;
    }

    private void validateRelationships(Map<String, String> values)
    {
        less(values, "return_watch", "return_limit", "退货阈值需满足 th_watch < th_limit < th_ban");
        less(values, "return_limit", "return_ban", "退货阈值需满足 th_watch < th_limit < th_ban");
        less(values, "margin_lower", "margin_upper", "毛利率下限须小于上限");
        less(values, "adi_lower", "adi_upper", "ADI下限须小于上限");
        less(values, "quality_full_rate", "quality_zero_rate", "质量满分线须小于归零线");
        String[] grades = {"D", "C", "B", "A", "S"};
        for (int i = 0; i < grades.length - 1; i++)
            less(values, "grade_" + grades[i], "grade_" + grades[i + 1], "等级下限分须满足 S > A > B > C > D");
        for (String shape : List.of("smooth", "intermittent", "erratic", "lumpy", "no_sales"))
        {
            BigDecimal total = BigDecimal.ZERO;
            for (String window : List.of("w7", "w15", "w30")) total = total.add(new BigDecimal(values.get("pattern_" + shape + "_" + window)));
            if (total.compareTo(BigDecimal.ONE) != 0 && !("no_sales".equals(shape) && total.signum() == 0))
                throw new ServiceException("各形态的w7/w15/w30权重合计须为1，无销量形态也可全部为0");
        }
        BigDecimal total = modules.get(3).rows().stream().map(row -> new BigDecimal(values.get(row.fields().get(0).key())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        if (total.compareTo(BigDecimal.ONE) != 0) throw new ServiceException("七个维度的权重合计须为1（包括未启用的维度）");
    }

    private void less(Map<String, String> values, String lower, String upper, String message)
    {
        if (new BigDecimal(values.get(lower)).compareTo(new BigDecimal(values.get(upper))) >= 0)
            throw new ServiceException(message);
    }
}
