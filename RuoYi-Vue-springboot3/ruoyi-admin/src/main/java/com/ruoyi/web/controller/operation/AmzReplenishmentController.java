package com.ruoyi.web.controller.operation;

import java.util.ArrayList;
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
import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.enums.BusinessType;
import java.math.BigDecimal;
import java.util.Map;

import com.ruoyi.system.domain.operation.AmzSalesBreakdownRequest;
import com.ruoyi.system.domain.operation.EbayReplenishmentSearchRequest;
import com.ruoyi.system.domain.operation.ExportRequest;
import com.ruoyi.system.domain.operation.external.AmzReplenishmentOverride;
import com.ruoyi.system.mapper.operation.external.AmzReplenishmentOverrideMapper;
import com.ruoyi.system.mapper.operation.external.AmzWarehouseInventoryDetailMapper;
import com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService;
import com.ruoyi.system.service.operation.UnifiedExportService;
import com.github.pagehelper.PageHelper;
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(name = "Amazon补货")
@RestController
@RequestMapping("/operations/amz/replenishment")
public class AmzReplenishmentController extends BaseController
{
    @Autowired
    private IAmzReplenishmentSnapshotService snapshotService;
    @Autowired
    private UnifiedExportService exportService;
    @Autowired
    private AmzReplenishmentOverrideMapper overrideMapper;
    @Autowired
    private AmzWarehouseInventoryDetailMapper inventoryMapper;
    @Autowired
    private RedisCache redisCache;

    // ====== 美国组 / 欧洲组独立查询 ======
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/us/search")
    public TableDataInfo searchUs(@RequestBody EbayReplenishmentSearchRequest req)
    {
        return searchInternal(forceRegion(req, "US"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/eu/search")
    public TableDataInfo searchEu(@RequestBody EbayReplenishmentSearchRequest req)
    {
        return searchInternal(forceRegion(req, "EU"));
    }

    private TableDataInfo searchInternal(EbayReplenishmentSearchRequest req)
    {
        PageHelper.startPage(req.getPageNum() != null ? req.getPageNum() : 1,
                             req.getPageSize() != null ? req.getPageSize() : 20);
        return getDataTable(snapshotService.search(req));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/us/distinct-values")
    public AjaxResult distinctUsValues(@RequestParam String field, @RequestParam(required = false) String keyword)
    {
        return AjaxResult.success(snapshotService.distinctValues(field, keyword, "US"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/eu/distinct-values")
    public AjaxResult distinctEuValues(@RequestParam String field, @RequestParam(required = false) String keyword)
    {
        return AjaxResult.success(snapshotService.distinctValues(field, keyword, "EU"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/us/store-names")
    public AjaxResult usStoreNames()
    {
        return AjaxResult.success(snapshotService.distinctValues("storeName", null, "US"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/eu/store-names")
    public AjaxResult euStoreNames()
    {
        return AjaxResult.success(snapshotService.distinctValues("storeName", null, "EU"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/us/warehouse-names")
    public AjaxResult usWarehouseNames()
    {
        return AjaxResult.success(snapshotService.distinctValues("warehouseName", null, "US"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @GetMapping("/eu/warehouse-names")
    public AjaxResult euWarehouseNames()
    {
        return AjaxResult.success(snapshotService.distinctValues("warehouseName", null, "EU"));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/us/sales-breakdown/search")
    public AjaxResult usSalesBreakdown(@RequestBody AmzSalesBreakdownRequest req)
    {
        forceRegion(req, "US");
        return AjaxResult.success(snapshotService.salesBreakdown(req));
    }

    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/eu/sales-breakdown/search")
    public AjaxResult euSalesBreakdown(@RequestBody AmzSalesBreakdownRequest req)
    {
        forceRegion(req, "EU");
        return AjaxResult.success(snapshotService.salesBreakdown(req));
    }

    // ====== 两套独立刷新 ======
    @Log(title = "Amazon美国组补货", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/us/refresh")
    public AjaxResult refreshUs()
    {
        return refreshRegion("US");
    }

    @Log(title = "Amazon欧洲组补货", businessType = BusinessType.OTHER)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping("/eu/refresh")
    public AjaxResult refreshEu()
    {
        return refreshRegion("EU");
    }

    // ====== 两套独立导出 ======
    @Log(title = "Amazon美国组补货", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:export')")
    @PostMapping("/us/export")
    public void exportUs(@RequestBody ExportRequest req, HttpServletResponse response) throws Exception
    {
        exportRegion(forceRegion(req, "US"), response, "us");
    }

    @Log(title = "Amazon欧洲组补货", businessType = BusinessType.EXPORT)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:export')")
    @PostMapping("/eu/export")
    public void exportEu(@RequestBody ExportRequest req, HttpServletResponse response) throws Exception
    {
        exportRegion(forceRegion(req, "EU"), response, "eu");
    }

    /** 保存人工覆盖：产品分类/已采购数量 */
    @Log(title = "AMZ补货-人工覆盖", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping({"/us/override", "/eu/override"})
    public AjaxResult saveOverride(@RequestBody Map<String, Object> body)
    {
        String sid = body.get("sid") != null ? String.valueOf(body.get("sid")) : null;
        String sellerSku = (String) body.get("sellerSku");
        if (sid == null || sellerSku == null) return error("sid和sellerSku必填");
        AmzReplenishmentOverride ov = new AmzReplenishmentOverride();
        ov.setSid(sid);
        ov.setSellerSku(sellerSku);
        boolean hasProductCategory = body.containsKey("productCategory");
        boolean hasManualPurchasedQty = body.containsKey("manualPurchasedQty");
        boolean hasRemark = body.containsKey("remark");
        if (hasProductCategory)
            ov.setProductCategory((String) body.get("productCategory"));
        if (hasManualPurchasedQty) {
            Object v = body.get("manualPurchasedQty");
            ov.setManualPurchasedQty(v != null && !"".equals(v) ? new BigDecimal(String.valueOf(v)) : null);
        }
        if (hasRemark)
            ov.setRemark((String) body.get("remark"));
        if (hasProductCategory) overrideMapper.upsertProductCategory(ov);
        if (hasManualPurchasedQty) overrideMapper.upsertManualPurchasedQty(ov);
        if (hasRemark) overrideMapper.upsertRemark(ov);
        return success();
    }

    /** 直接修改库存表的待到货量（已采购数量 = quantity_receive + product_qc_num） */
    @Log(title = "AMZ补货-修改已采购", businessType = BusinessType.UPDATE)
    @PreAuthorize("@ss.hasPermi('operations:amzReplenishment:list')")
    @PostMapping({"/us/update-qty-receive", "/eu/update-qty-receive"})
    public AjaxResult updateQtyReceive(@RequestBody Map<String, Object> body)
    {
        String warehouseSku = (String) body.get("warehouseSku");
        String warehouseName = (String) body.get("warehouseName");
        if (warehouseSku == null || warehouseSku.isBlank() || warehouseName == null || warehouseName.isBlank())
            return error("仓库SKU和仓库名称必填");
        BigDecimal v = body.get("value") != null ? new BigDecimal(String.valueOf(body.get("value"))) : BigDecimal.ZERO;
        int rows = inventoryMapper.updateQuantityReceive(warehouseSku, warehouseName, v);
        if (rows <= 0) return error("未找到对应仓库的SKU库存记录");
        return success();
    }

    private EbayReplenishmentSearchRequest forceRegion(EbayReplenishmentSearchRequest req, String region)
    {
        if (req == null) req = new EbayReplenishmentSearchRequest();
        List<EbayReplenishmentSearchRequest.FilterItem> filters = req.getFilters() == null
                ? new ArrayList<>() : new ArrayList<>(req.getFilters());
        filters.removeIf(item -> "regionGroup".equals(item.getField()));
        filters.add(new EbayReplenishmentSearchRequest.FilterItem("regionGroup", region));
        req.setFilters(filters);
        return req;
    }

    private ExportRequest forceRegion(ExportRequest req, String region)
    {
        if (req == null) req = new ExportRequest();
        List<EbayReplenishmentSearchRequest.FilterItem> filters = req.getFilters() == null
                ? new ArrayList<>() : new ArrayList<>(req.getFilters());
        filters.removeIf(item -> "regionGroup".equals(item.getField()));
        filters.add(new EbayReplenishmentSearchRequest.FilterItem("regionGroup", region));
        req.setFilters(filters);
        return req;
    }

    private AjaxResult refreshRegion(String region)
    {
        return withLock("lock:sync:lingxing:amz", 1800, "AMZ数据同步或刷新正在执行中，请稍后再试", () -> {
            snapshotService.refreshSnapshot(region);
            return success();
        });
    }

    private void exportRegion(ExportRequest req, HttpServletResponse response, String region) throws Exception
    {
        withLock("lock:export:amz:replenishment:" + region, 300, "AMZ补货导出正在执行中，请稍后再试", () -> {
            exportService.exportAmzReplenishment(req, response);
            return null;
        });
    }

    // ==================== 锁工具 ====================
    @FunctionalInterface
    private interface LockedAction { AjaxResult run() throws Exception; }

    private AjaxResult withLock(String key, long timeoutSec, String busyMsg, LockedAction action)
    {
        if (!redisCache.tryLock(key, timeoutSec)) return error(busyMsg);
        try { return action.run(); }
        catch (Exception e) { return error(e.getMessage()); }
        finally { redisCache.unlock(key); }
    }
}
