package com.ruoyi.web.controller.operation;

import java.util.List;

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
        mapper.insert(config);
        return success();
    }

    @Log(title = "AMZ公式配置", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PutMapping("/update")
    public AjaxResult edit(@RequestBody AmzFormulaConfig config)
    {
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
}
