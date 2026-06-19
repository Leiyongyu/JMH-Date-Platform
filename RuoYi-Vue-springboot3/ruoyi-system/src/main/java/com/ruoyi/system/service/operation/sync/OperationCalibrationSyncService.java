package com.ruoyi.system.service.operation.sync;

import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.goodcang.*;
import com.ruoyi.system.service.operation.external.lingxing.*;
import java.time.LocalDate;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 数据校准全量拉取服务 —— 开发期用，按日期分段拉取历史数据，upsert 不清空。
 */
@Service
public class OperationCalibrationSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(OperationCalibrationSyncService.class);
    private static final String API = "/operations/sync/calibration/full";

    public Map<String, Object> runFullCalibration(LocalDate startDate, LocalDate endDate,
                                                   boolean ebay, boolean amz, boolean inventoryPurchase, boolean goodcang)
    {
        long totalStart = System.currentTimeMillis();
        IOperationSyncLogService logSvc = SpringUtils.getBean(IOperationSyncLogService.class);
        Long parentId = logSvc.start("calibration", "数据校准全量拉取", API, "MANUAL", "SYSTEM", null, null);

        List<Map<String, Object>> results = new ArrayList<>();
        int ok = 0, fail = 0;

        // 1. 店铺（不分平台，一次拉）
        runStep(logSvc, parentId, results, "shop_list", "领星-店铺列表", () ->
            SpringUtils.getBean(LingxingShopSyncService.class).syncShops());

        // 2. 领星仓库
        runStep(logSvc, parentId, results, "warehouse", "领星-仓库信息", () ->
            SpringUtils.getBean(LingxingWarehouseSyncService.class).syncWarehouses());

        if (ebay) {
            // 3. eBay Listing
            runStep(logSvc, parentId, results, "ebay_listing", "领星-eBay商品刊登", () ->
                SpringUtils.getBean(LingxingEbaySyncService.class).syncAll());
            // 4. 库存明细
            runStep(logSvc, parentId, results, "lingxing_inv", "领星-库存明细", () ->
                SpringUtils.getBean(LingxingInventorySyncService.class).syncAll());
        }

        if (goodcang) {
            // 5-8 谷仓
            runStep(logSvc, parentId, results, "gc_wh", "谷仓-仓库信息", () ->
                SpringUtils.getBean(GoodcangWarehouseSyncService.class).syncWarehouses());
            runStep(logSvc, parentId, results, "gc_product", "谷仓-商品信息", () ->
                SpringUtils.getBean(GoodcangProductSyncService.class).syncFromApi());
            runStep(logSvc, parentId, results, "gc_grn_list", "谷仓-入库单(全量)", () ->
                SpringUtils.getBean(GoodcangGrnSyncService.class).syncGrnListAll());
            runStep(logSvc, parentId, results, "gc_grn_detail", "谷仓-入库单详情", () ->
                SpringUtils.getBean(GoodcangGrnSyncService.class).syncAllGrnDetails());
        }

        if (inventoryPurchase) {
            // 9-11 库存流水+采购
            runStep(logSvc, parentId, results, "statement", "领星-库存流水", () ->
                SpringUtils.getBean(LingxingStatementSyncService.class).sync(startDate, endDate, 30));
            runStep(logSvc, parentId, results, "purchase_order", "领星-采购单", () ->
                SpringUtils.getBean(LingxingPurchaseOrderSyncService.class).sync(startDate, endDate, 90));
            runStep(logSvc, parentId, results, "purchase_plan", "领星-采购计划", () ->
                SpringUtils.getBean(LingxingPurchasePlanSyncService.class).sync(startDate, endDate, 90));
        }

        if (amz) {
            // 12-15 AMZ
            runStep(logSvc, parentId, results, "amz_listing", "领星-Amazon商品刊登", () ->
                SpringUtils.getBean(LingxingAmzListingSyncService.class).syncAll());
            runStep(logSvc, parentId, results, "amz_profit", "领星-Amazon订单利润", () ->
                SpringUtils.getBean(AmzOrderProfitSyncService.class).syncAll());
            runStep(logSvc, parentId, results, "amz_restock", "领星-Amazon补货建议", () ->
                SpringUtils.getBean(AmzRestockSummarySyncService.class).syncAll());
            runStep(logSvc, parentId, results, "amz_inv", "领星-Amazon库存明细", () ->
                SpringUtils.getBean(AmzWarehouseInventorySyncService.class).syncAll());
        }

        // 16-18 刷新快照
        for (String[] snap : new String[][]{{"ebay_replenish","刷新eBay补货快照"},{"ebay_tracking","刷新eBay跟价快照"},{"amz_replenish","刷新Amazon补货快照"}}) {
            runStep(logSvc, parentId, results, snap[0], snap[1], () -> {
                switch (snap[0]) {
                    case "ebay_replenish": SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService.class).refreshSnapshot(); break;
                    case "ebay_tracking": SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayPriceTrackingService.class).refreshSnapshot(); break;
                    case "amz_replenish": SpringUtils.getBean(com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService.class).refreshSnapshot(); break;
                }
                return OperationSyncResult.success(snap[0], snap[1], "compute", 1, 1, 0);
            });
        }

        // 计数
        for (Map<String, Object> r : results) {
            if ("SUCCESS".equals(r.get("status"))) ok++; else fail++;
        }
        long elapsed = System.currentTimeMillis() - totalStart;

        OperationSyncResult parentResult = new OperationSyncResult();
        parentResult.setSyncType("calibration"); parentResult.setSyncName("数据校准全量拉取");
        parentResult.setStatus(fail == 0 ? "SUCCESS" : (ok > 0 ? "PARTIAL_SUCCESS" : "FAILED"));
        parentResult.setTotalCount(results.size()); parentResult.setSuccessCount(ok);
        parentResult.setFailCount(fail); parentResult.setElapsedMs(elapsed);
        logSvc.finish(parentId, parentResult);

        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("parentLogId", parentId); resp.put("status", parentResult.getStatus());
        resp.put("totalSteps", results.size()); resp.put("successSteps", ok);
        resp.put("failedSteps", fail); resp.put("elapsed", elapsed / 1000.0 + "s");
        resp.put("steps", results);
        return resp;
    }

    private void runStep(IOperationSyncLogService logSvc, Long parentId, List<Map<String, Object>> results,
                          String key, String name, java.util.concurrent.Callable<OperationSyncResult> action)
    {
        long t = System.currentTimeMillis();
        Long childId = logSvc.start("calibration."+key, name, "", "MANUAL", "SYSTEM", null, null, parentId);
        try {
            OperationSyncResult r = action.call();
            r.setElapsedMs(System.currentTimeMillis()-t);
            logSvc.finish(childId, r);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("key", key); m.put("name", name); m.put("status", r.getStatus());
            m.put("total", r.getTotalCount()); m.put("success", r.getSuccessCount());
            m.put("fail", r.getFailCount()); m.put("error", r.getErrorMessage());
            results.add(m);
        } catch (Exception e) {
            LOG.error("校准步骤[{}]失败: {}", name, e.getMessage());
            OperationSyncResult fr = OperationSyncResult.failed("calibration."+key, name, "", e.getMessage(), System.currentTimeMillis()-t);
            logSvc.finish(childId, fr);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("key", key); m.put("name", name); m.put("status", "FAILED");
            m.put("error", e.getMessage());
            results.add(m);
        }
    }
}
