package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.external.LingxingLogisticsChannel;
import com.ruoyi.system.mapper.operation.external.LingxingLogisticsChannelMapper;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;

/** 领星头程物流渠道全量同步。 */
@Service
public class LingxingLogisticsChannelSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingLogisticsChannelSyncService.class);
    private static final String API_PATH = "erp/sc/data/local_inventory/channelList";
    private static final int PAGE_SIZE = 20;
    private static final int MAX_PAGES = 1000;
    private static final long RATE_LIMIT_DELAY_MS = 1100L;
    private static final DateTimeFormatter DATE_TIME_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final LingxingGatewayService gateway;
    private final LingxingLogisticsChannelMapper mapper;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactionTemplate;

    public LingxingLogisticsChannelSyncService(
            LingxingGatewayService gateway,
            LingxingLogisticsChannelMapper mapper,
            ObjectMapper objectMapper,
            TransactionTemplate transactionTemplate)
    {
        this.gateway = gateway;
        this.mapper = mapper;
        this.objectMapper = objectMapper;
        this.transactionTemplate = transactionTemplate;
    }

    public OperationSyncResult syncAll() throws Exception
    {
        long start = System.currentTimeMillis();
        LinkedHashMap<Long, LingxingLogisticsChannel> allRows = new LinkedHashMap<>();
        Integer expectedTotal = null;
        int offset = 0;

        for (int page = 0; page < MAX_PAGES; page++)
        {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("offset", offset);
            body.put("length", PAGE_SIZE);
            Map<String, Object> response = gateway.post(API_PATH, body);
            validateResponse(response);

            if (expectedTotal == null)
            {
                expectedTotal = integerValue(response.get("total"));
                if (expectedTotal == null)
                {
                    throw new IllegalStateException(
                            "领星物流渠道接口缺少有效 total，已终止同步并保留原表");
                }
            }
            List<Map<String, Object>> data = dataList(response.get("data"));
            for (Map<String, Object> row : data)
            {
                LingxingLogisticsChannel channel = toEntity(row);
                if (channel.getId() == null)
                {
                    throw new IllegalStateException("领星物流渠道返回缺少 id，已终止同步并保留原表");
                }
                if (allRows.put(channel.getId(), channel) != null)
                {
                    throw new IllegalStateException(
                            "领星物流渠道返回重复 id=" + channel.getId() + "，已终止同步并保留原表");
                }
            }

            offset += data.size();
            LOG.info("领星物流渠道已拉取 offset={}, 本页={}, total={}",
                    offset, data.size(), expectedTotal);
            if (data.isEmpty() || (expectedTotal != null && offset >= expectedTotal))
            {
                break;
            }
            Thread.sleep(RATE_LIMIT_DELAY_MS);
        }

        int remoteTotal = expectedTotal == null ? allRows.size() : expectedTotal;
        if (remoteTotal <= 0)
        {
            return OperationSyncResult.failed(
                    "lingxing_logistics_channel",
                    "领星-头程物流渠道",
                    API_PATH,
                    "领星返回总数为0，为保护已有数据未清空本地表",
                    System.currentTimeMillis() - start);
        }
        if (allRows.size() != remoteTotal)
        {
            return OperationSyncResult.failed(
                    "lingxing_logistics_channel",
                    "领星-头程物流渠道",
                    API_PATH,
                    "分页拉取不完整：接口total=" + remoteTotal + "，实际去重后=" + allRows.size()
                            + "，已保留原表",
                    System.currentTimeMillis() - start);
        }

        List<LingxingLogisticsChannel> channels = new ArrayList<>(allRows.values());
        transactionTemplate.executeWithoutResult(status -> {
            mapper.deleteAll();
            mapper.batchInsert(channels);
        });

        return OperationSyncResult.success(
                "lingxing_logistics_channel",
                "领星-头程物流渠道",
                API_PATH,
                remoteTotal,
                channels.size(),
                System.currentTimeMillis() - start);
    }

    private void validateResponse(Map<String, Object> response)
    {
        if (response == null)
        {
            throw new IllegalStateException("领星物流渠道接口返回空响应");
        }
        Integer code = integerValue(response.get("code"));
        if (code == null || code != 0)
        {
            Object message = response.get("message") != null
                    ? response.get("message") : response.get("msg");
            throw new IllegalStateException(
                    "领星物流渠道接口失败，code=" + code + "，message=" + message);
        }
    }

    private LingxingLogisticsChannel toEntity(Map<String, Object> row) throws Exception
    {
        LingxingLogisticsChannel entity = new LingxingLogisticsChannel();
        entity.setId(longValue(row.get("id")));
        entity.setChannelName(textValue(row.get("channel_name")));
        entity.setMethodId(textValue(row.get("method_id")));
        entity.setMethodName(textValue(row.get("method_name")));
        entity.setBillingType(integerValue(row.get("billing_type")));
        entity.setVolumeCalcParam(textValue(row.get("volume_calc_param")));
        entity.setZipCode(textValue(row.get("zip_code")));
        entity.setValidPeriod(integerValue(row.get("valid_period")));
        entity.setRemark(textValue(row.get("remark")));
        entity.setEnabled(integerValue(row.get("enabled")));
        entity.setLastModifyUid(longValue(row.get("last_modify_uid")));
        entity.setGmtModified(dateTimeValue(row.get("gmt_modified")));

        Map<String, Object> provider = mapValue(row.get("provider"));
        entity.setProviderId(textValue(provider.get("id")));
        entity.setProviderName(textValue(provider.get("logistics_provider_name")));
        entity.setFreightJson(objectMapper.writeValueAsString(
                row.get("freight") == null ? List.of() : row.get("freight")));
        entity.setSendPlaceCode(textValue(row.get("send_place_code")));
        entity.setReceiveCountryCode(textValue(row.get("receive_country_code")));
        entity.setIsIncludeTax(integerValue(row.get("is_include_tax")));
        entity.setIsPointsBehind(integerValue(row.get("is_points_behind")));
        entity.setPointsBehindCoefficient(decimalValue(row.get("points_behind_coeffient")));
        entity.setRawJson(objectMapper.writeValueAsString(row));
        LocalDateTime now = LocalDateTime.now();
        entity.setCreateTime(now);
        entity.setUpdateTime(now);
        return entity;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> dataList(Object value)
    {
        if (value == null) return new ArrayList<>();
        if (value instanceof List<?>) return (List<Map<String, Object>>) value;
        return objectMapper.convertValue(value,
                new TypeReference<List<Map<String, Object>>>() {});
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value)
    {
        if (value instanceof Map<?, ?>) return (Map<String, Object>) value;
        if (value == null) return new LinkedHashMap<>();
        return objectMapper.convertValue(value,
                new TypeReference<Map<String, Object>>() {});
    }

    private String textValue(Object value)
    {
        if (value == null) return null;
        String text = String.valueOf(value);
        return StringUtils.hasText(text) ? text : null;
    }

    private Integer integerValue(Object value)
    {
        String text = textValue(value);
        if (text == null) return null;
        try { return new BigDecimal(text).intValueExact(); }
        catch (Exception ignored) { return null; }
    }

    private Long longValue(Object value)
    {
        String text = textValue(value);
        if (text == null) return null;
        try { return new BigDecimal(text).longValueExact(); }
        catch (Exception ignored) { return null; }
    }

    private BigDecimal decimalValue(Object value)
    {
        String text = textValue(value);
        if (text == null) return null;
        try { return new BigDecimal(text); }
        catch (Exception ignored) { return null; }
    }

    private LocalDateTime dateTimeValue(Object value)
    {
        String text = textValue(value);
        if (text == null) return null;
        try { return LocalDateTime.parse(text, DATE_TIME_FORMAT); }
        catch (Exception ignored) { return null; }
    }
}
