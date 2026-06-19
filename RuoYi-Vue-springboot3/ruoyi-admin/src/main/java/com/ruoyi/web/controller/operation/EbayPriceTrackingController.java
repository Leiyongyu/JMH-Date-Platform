package com.ruoyi.web.controller.operation;

import java.util.List;
import java.util.Map;

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
import com.ruoyi.system.domain.operation.EbayPriceTrackingSnapshot;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.ExportRequest;
import com.ruoyi.system.domain.operation.external.EbayLinkTemplate;
import com.ruoyi.system.service.operation.IEbayPriceTrackingService;
import com.ruoyi.system.service.operation.OperationImportService;
import com.ruoyi.system.service.operation.UnifiedExportService;
import com.github.pagehelper.PageHelper;

@RestController
@RequestMapping("/operations/ebay/price-tracking")
public class EbayPriceTrackingController extends BaseController
{
    @Autowired
    private IEbayPriceTrackingService priceTrackingService;
    @Autowired
    private OperationImportService importService;
    @Autowired
    private UnifiedExportService exportService;

    // ====== 搜索 ======
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/search")
    public TableDataInfo search(@RequestBody EbayReplenishmentSearchRequest req)
    {
        PageHelper.startPage(req.getPageNum() != null ? req.getPageNum() : 1,
                             req.getPageSize() != null ? req.getPageSize() : 20);
        List<EbayPriceTrackingSnapshot> list = priceTrackingService.search(req);
        return getDataTable(list);
    }

    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @GetMapping("/distinct-values")
    public AjaxResult distinctValues(@RequestParam String field, @RequestParam(required = false) String keyword)
    {
        return AjaxResult.success(priceTrackingService.distinctValues(field, keyword));
    }

    // ====== 刷新 ======
    @Log(title = "eBay跟价", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/refresh")
    public AjaxResult refresh()
    {
        priceTrackingService.refreshSnapshot();
        return success();
    }

    // ====== 跟卖利润率 & 底线价计算 ======
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/calc-tracking")
    public AjaxResult calcTracking(@RequestBody Map<String, String> body)
    {
        Map<String, Object> result = priceTrackingService.calcTracking(
                body.get("site"), body.get("sku"), body.get("trackingPrice"));
        return AjaxResult.success(result);
    }

    // ====== 保存操作（写 config 表，乐观锁 + 操作日志） ======
    @Log(title = "eBay跟价-保存跟卖价", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/save-tracking-price")
    public AjaxResult saveTrackingPrice(@RequestBody Map<String, String> body)
    {
        priceTrackingService.saveTrackingPrice(body.get("site"), body.get("sku"), body.get("trackingPrice"));
        return success();
    }

    @Log(title = "eBay跟价-保存OE号", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/oe")
    public AjaxResult saveOe(@RequestBody Map<String, String> body)
    {
        return AjaxResult.success(priceTrackingService.saveOeNumber(
                body.get("site"), body.get("sku"), body.get("oeNumber")));
    }

    @Log(title = "eBay跟价-保存备注", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/remark")
    public AjaxResult saveRemark(@RequestBody Map<String, String> body)
    {
        priceTrackingService.saveRemark(body.get("site"), body.get("sku"), body.get("remark"));
        return success();
    }

    // ====== 链接模板 ======
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @GetMapping("/link-template")
    public AjaxResult listLinkTemplates()
    {
        return AjaxResult.success(priceTrackingService.listLinkTemplates());
    }

    @Log(title = "eBay跟价-保存链接模板", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @PostMapping("/link-template")
    public AjaxResult saveLinkTemplate(@RequestBody EbayLinkTemplate template)
    {
        priceTrackingService.saveLinkTemplate(template);
        return success();
    }

    @Log(title = "eBay跟价-删除链接模板", businessType = BusinessType.DELETE)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:list')")
    @DeleteMapping("/link-template/{site}")
    public AjaxResult deleteLinkTemplate(@PathVariable String site)
    {
        priceTrackingService.deleteLinkTemplate(site);
        return success();
    }

    // ====== 导出 ======
    @Log(title = "eBay跟价", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:export')")
    @PostMapping("/export")
    public void export(@RequestBody ExportRequest req, HttpServletResponse response) throws Exception
    {
        exportService.exportEbayPriceTracking(req, response);
    }

    // ====== 导入（最低价/商品单价） ======
    @Log(title = "eBay跟价-导入最低价", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:import')")
    @PostMapping("/import-lowest-price")
    public AjaxResult importLowestPrice(@RequestParam("file") MultipartFile file)
    {
        try { return AjaxResult.success(importService.importLowestPrice(file, SecurityUtils.getUsername())); }
        catch (Exception e) { return error(e.getMessage()); }
    }

    @Log(title = "eBay跟价-导入商品单价", businessType = BusinessType.IMPORT)
    @PreAuthorize("@ss.hasPermi('operations:ebayReplenishment:import')")
    @PostMapping("/import-product-price")
    public AjaxResult importProductPrice(@RequestParam("file") MultipartFile file)
    {
        try { return AjaxResult.success(importService.importProductPrice(file, SecurityUtils.getUsername())); }
        catch (Exception e) { return error(e.getMessage()); }
    }
}
