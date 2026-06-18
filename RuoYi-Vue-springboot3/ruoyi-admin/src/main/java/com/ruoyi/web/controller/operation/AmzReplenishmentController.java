package com.ruoyi.web.controller.operation;

import java.util.List;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.system.domain.operation.AmzReplenishmentSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService;

@RestController
@RequestMapping("/operations/amz/replenishment")
public class AmzReplenishmentController extends BaseController
{
    @Autowired
    private IAmzReplenishmentSnapshotService snapshotService;

    // ====== 基础列表 ======
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/list")
    public TableDataInfo list(AmzReplenishmentSnapshot snapshot)
    {
        startPage();
        return getDataTable(snapshotService.selectAmzReplenishmentSnapshotList(snapshot));
    }

    // ====== 增强搜索 ======
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/search")
    public TableDataInfo search(@RequestBody EbayReplenishmentSearchRequest req)
    {
        startPage(req.getPageNum(), req.getPageSize());
        return getDataTable(snapshotService.search(req));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/distinct-values")
    public AjaxResult distinctValues(@RequestParam String field, @RequestParam(required = false) String keyword)
    {
        return AjaxResult.success(snapshotService.distinctValues(field, keyword));
    }

    // ====== 刷新 ======
    @Log(title = "Amazon补货", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/refresh")
    public AjaxResult refresh()
    {
        snapshotService.refreshSnapshot();
        return success();
    }

    // ====== 导出 ======
    @Log(title = "Amazon补货", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:export')")
    @PostMapping("/export")
    public void export(HttpServletResponse response, AmzReplenishmentSnapshot snapshot)
    {
        List<AmzReplenishmentSnapshot> list = snapshotService.selectAmzReplenishmentSnapshotList(snapshot);
        ExcelUtil<AmzReplenishmentSnapshot> util = new ExcelUtil<>(AmzReplenishmentSnapshot.class);
        util.exportExcel(response, list, "Amazon补货数据");
    }
}
