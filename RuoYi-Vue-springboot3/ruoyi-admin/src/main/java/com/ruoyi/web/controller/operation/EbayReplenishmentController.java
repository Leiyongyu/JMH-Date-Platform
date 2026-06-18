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
import org.springframework.web.multipart.MultipartFile;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.EbayReplenishmentSnapshot;
import com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService;
import com.ruoyi.system.service.operation.OperationImportService;
import com.github.pagehelper.PageHelper;

@RestController
@RequestMapping("/operations/ebay/replenishment")
public class EbayReplenishmentController extends BaseController
{
    @Autowired
    private IEbayReplenishmentSnapshotService snapshotService;
    @Autowired
    private OperationImportService importService;

    // ========================================================================
    // 基础列表（若依兼容，保留）
    // ========================================================================

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @GetMapping("/list")
    public TableDataInfo list(EbayReplenishmentSnapshot snapshot)
    {
        startPage();
        List<EbayReplenishmentSnapshot> list = snapshotService.selectEbayReplenishmentSnapshotList(snapshot);
        return getDataTable(list);
    }

    // ========================================================================
    // 新版搜索：多字段文本/数值筛选全部下推 SQL
    // ========================================================================

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/search")
    public TableDataInfo search(@RequestBody EbayReplenishmentSearchRequest req)
    {
        PageHelper.startPage(req.getPageNum() != null ? req.getPageNum() : 1,
                             req.getPageSize() != null ? req.getPageSize() : 20);
        List<EbayReplenishmentSnapshot> list = snapshotService.search(req);
        return getDataTable(list);
    }

    /** 列头筛选候选值 —— SQL distinct，不再 Java 内存去重 */
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @GetMapping("/distinct-values")
    public AjaxResult distinctValues(
            @RequestParam String field,
            @RequestParam(required = false) String keyword)
    {
        List<String> values = snapshotService.distinctValues(field, keyword);
        return AjaxResult.success(values);
    }

    // ========================================================================
    // 导出 & 刷新
    // ========================================================================

    @Log(title = "eBay补货", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:export')")
    @PostMapping("/export")
    public void export(HttpServletResponse response, EbayReplenishmentSnapshot snapshot)
    {
        List<EbayReplenishmentSnapshot> list = snapshotService.selectEbayReplenishmentSnapshotList(snapshot);
        ExcelUtil<EbayReplenishmentSnapshot> util = new ExcelUtil<>(EbayReplenishmentSnapshot.class);
        util.exportExcel(response, list, "eBay补货数据");
    }

    @Log(title = "eBay补货", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/refresh")
    public AjaxResult refresh()
    {
        snapshotService.refreshSnapshot();
        return success();
    }

    // ====== 导入 ======
    @Log(title = "eBay补货-导入销量", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:import')")
    @PostMapping("/import-sales")
    public AjaxResult importSales(@RequestParam("file") MultipartFile file)
    {
        try { return AjaxResult.success(importService.importEbaySales(file, SecurityUtils.getUsername())); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "eBay补货-导入利润率", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:import')")
    @PostMapping("/import-profit-rate")
    public AjaxResult importProfitRate(@RequestParam("file") MultipartFile file)
    {
        try { return AjaxResult.success(importService.importProfitRate(file, SecurityUtils.getUsername())); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "eBay补货-导入退货率", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:import')")
    @PostMapping("/import-return-rate")
    public AjaxResult importReturnRate(@RequestParam("file") MultipartFile file)
    {
        try { return AjaxResult.success(importService.importReturnRate(file, SecurityUtils.getUsername())); }
        catch (Exception e) { return error(e.getMessage()); }
    }
}
