package com.ruoyi.web.controller.operation;

import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.domain.operation.external.AmzFormulaConfig;
import com.ruoyi.system.mapper.operation.external.AmzFormulaConfigMapper;
import com.ruoyi.system.mapper.operation.external.WarehouseMapper;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(name = "AMZ补货公式配置")
@RestController
@RequestMapping("/operations/amz/formula-config")
public class AmzFormulaConfigController extends BaseController
{
    @Autowired
    private AmzFormulaConfigMapper mapper;
    @Autowired
    private WarehouseMapper warehouseMapper;

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/list")
    public AjaxResult list()
    {
        List<AmzFormulaConfig> list = mapper.selectAll();
        return success(list);
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/{id}")
    public AjaxResult get(@PathVariable Long id)
    {
        return success(mapper.selectById(id));
    }

    @Log(title = "AMZ公式配置", businessType = BusinessType.INSERT)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/add")
    public AjaxResult add(@RequestBody AmzFormulaConfig config)
    {
        String validation = validateConfig(config);
        if (validation != null) return error(validation);
        mapper.insert(config);
        return success();
    }

    @Log(title = "AMZ公式配置", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PutMapping("/update")
    public AjaxResult edit(@RequestBody AmzFormulaConfig config)
    {
        if (config.getId() == null) return error("配置ID不能为空");
        String validation = validateConfig(config);
        if (validation != null) return error(validation);
        mapper.updateById(config);
        return success();
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/warehouses")
    public AjaxResult warehouses()
    {
        List<String> names = warehouseMapper.selectAll().stream()
            .filter(w -> w.getName() != null && w.getName().contains("AMZ"))
            .map(w -> w.getName())
            .distinct().sorted().collect(java.util.stream.Collectors.toList());
        return success(names);
    }

    private String validateConfig(AmzFormulaConfig config)
    {
        if (config == null) return "配置不能为空";
        String group = config.getRegionGroup() == null ? "" : config.getRegionGroup().trim().toUpperCase(Locale.ROOT);
        if (!"US".equals(group) && !"EU".equals(group)) return "区域组只能是US或EU";
        config.setRegionGroup(group);
        if (config.getRegionName() == null || config.getRegionName().trim().isEmpty()) return "区域名称不能为空";
        config.setRegionName(config.getRegionName().trim());

        BigDecimal w14 = config.getSalesWeight14d();
        BigDecimal w30 = config.getSalesWeight30d();
        BigDecimal w60 = config.getSalesWeight60d();
        if (w14 == null || w30 == null || w60 == null) return "销量权重不能为空";
        if (w14.signum() < 0 || w30.signum() < 0 || w60.signum() < 0) return "销量权重不能小于0";
        if (w14.add(w30).add(w60).subtract(BigDecimal.ONE).abs().compareTo(new BigDecimal("0.001")) > 0)
            return "14天、30天、60天销量权重合计必须等于1";
        if (!positive(config.getMonthMultiplier()) || !positive(config.getSafetyDays())
                || !positive(config.getShipDays()) || !positive(config.getReplenishDays()))
            return "月销、安全、发货和补货天数必须大于0";
        if (config.getMinReplenishQty() != null && config.getMaxReplenishQty() != null
                && config.getMinReplenishQty().compareTo(config.getMaxReplenishQty()) > 0)
            return "最小补货量不能大于最大补货量";
        if (config.getRoundMode() == null || !Set.of("NONE", "ROUND", "CEIL", "FLOOR").contains(config.getRoundMode()))
            return "取整方式不正确";

        Set<String> warehouses = splitWarehouses(config.getMarketplaces());
        if (warehouses.isEmpty()) return "至少选择一个匹配仓库";
        config.setMarketplaces(String.join(",", warehouses));
        if (config.getMarketplaces().length() > 200) return "匹配仓库内容过长";

        for (AmzFormulaConfig existing : mapper.selectAll())
        {
            if (config.getId() != null && config.getId().equals(existing.getId())) continue;
            if (group.equalsIgnoreCase(existing.getRegionGroup())) return "区域组" + group + "已存在配置";
            if (Integer.valueOf(1).equals(config.getEnabled()) && Integer.valueOf(1).equals(existing.getEnabled()))
            {
                Set<String> overlap = splitWarehouses(existing.getMarketplaces());
                overlap.retainAll(warehouses);
                if (!overlap.isEmpty()) return "仓库不能同时属于多个启用区域：" + String.join("、", overlap);
            }
        }
        return null;
    }

    private boolean positive(Integer value)
    {
        return value != null && value > 0;
    }

    private Set<String> splitWarehouses(String value)
    {
        Set<String> result = new java.util.LinkedHashSet<>();
        if (value == null) return result;
        for (String item : value.split(","))
        {
            String warehouse = item.trim();
            if (!warehouse.isEmpty()) result.add(warehouse);
        }
        return result;
    }
}
