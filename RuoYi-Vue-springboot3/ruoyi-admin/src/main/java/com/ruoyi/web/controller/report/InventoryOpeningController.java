package com.ruoyi.web.controller.report;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.system.domain.report.InventoryOpeningValue;
import com.ruoyi.system.service.report.IInventoryOpeningService;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 月初库存货值检查报表
 * <p>
 * 数据源: jmh_report.ads_monthly_opening_inventory_value
 */
@RestController
@RequestMapping("/report/inventory-opening")
public class InventoryOpeningController extends BaseController
{
    private final IInventoryOpeningService service;

    public InventoryOpeningController(IInventoryOpeningService service)
    {
        this.service = service;
    }

    @PreAuthorize("@ss.hasPermi('report:inventoryOpening:list')")
    @GetMapping("/list")
    public TableDataInfo list(InventoryOpeningValue query)
    {
        startPage();
        List<InventoryOpeningValue> list = service.selectList(query);
        return getDataTable(list);
    }

    @PreAuthorize("@ss.hasPermi('report:inventoryOpening:export')")
    @PostMapping("/export")
    public void export(HttpServletResponse response, InventoryOpeningValue query)
    {
        List<InventoryOpeningValue> list = service.selectList(query);
        ExcelUtil<InventoryOpeningValue> util = new ExcelUtil<>(InventoryOpeningValue.class);
        util.exportExcel(response, list, "月初库存货值检查");
    }
}
