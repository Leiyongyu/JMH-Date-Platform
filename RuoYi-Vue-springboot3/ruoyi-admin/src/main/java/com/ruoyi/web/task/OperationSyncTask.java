package com.ruoyi.web.task;

import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangGrnSyncService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangProductSyncService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangWarehouseSyncService;
import com.ruoyi.system.service.operation.external.lingxing.AmzOrderProfitSyncService;
import com.ruoyi.system.service.operation.external.lingxing.AmzRestockSummarySyncService;
import com.ruoyi.system.service.operation.external.lingxing.AmzWarehouseInventorySyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingAmzListingSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingEbaySyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingInventorySyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingPurchaseOrderSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingPurchasePlanSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingShopSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingStatementSyncService;
import com.ruoyi.system.service.operation.external.lingxing.AmzFbaShipmentSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingWarehouseSyncService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 运营数据同步定时任务。
 * 定时任务和手动同步共用 Redis 锁，避免接口拉取、导入、快照刷新互相覆盖。
 */
@Component("operationSyncTask")
public class OperationSyncTask
{
    private static final Logger LOG = LoggerFactory.getLogger(OperationSyncTask.class);
    private static final String LOCK_GLOBAL = "lock:sync:operation";
    private static final String LOCK_EBAY = "lock:sync:ebay";
    private static final String LOCK_AMZ = "lock:sync:amz";
    private static final int LOCK_TIMEOUT_SECONDS = 1800;

    // ==================== 低频基础同步 ====================
    public void syncGoodcangWarehouse() { exec("goodcang_warehouse", "谷仓-仓库信息", "/base_data/get_warehouse", LOCK_EBAY,
            () -> SpringUtils.getBean(GoodcangWarehouseSyncService.class).syncWarehouses()); }
    public void syncLingxingWarehouse() { exec("warehouse", "领星-仓库信息", "erp/sc/data/local_inventory/warehouse", LOCK_EBAY,
            () -> SpringUtils.getBean(LingxingWarehouseSyncService.class).syncWarehouses()); }
    public void syncLingxingShop() { exec("shop_list", "领星-店铺列表", "pb/mp/shop/v2/getSellerList", LOCK_EBAY,
            () -> SpringUtils.getBean(LingxingShopSyncService.class).syncShops()); }
    public void syncEbayListing() { exec("ebay_listing", "领星-eBay商品刊登", "basicOpen/multiplatform/ebay/list", LOCK_EBAY,
            () -> SpringUtils.getBean(LingxingEbaySyncService.class).syncAll()); }
    public void syncGoodcangProduct() { exec("goodcang_product", "谷仓-商品信息", "/product/get_product_sku_list", LOCK_EBAY,
            () -> SpringUtils.getBean(GoodcangProductSyncService.class).syncFromApi()); }
    public void syncAmzListing() { exec("amz_listing", "领星-Amazon商品刊登", "erp/sc/data/mws/listing", LOCK_AMZ,
            () -> SpringUtils.getBean(LingxingAmzListingSyncService.class).syncAll()); }

    // ==================== 每日高频同步 ====================
    public void syncLingxingInventory() { exec("lingxing_inventory", "领星-库存明细", "erp/sc/routing/data/local_inventory/inventoryDetails", LOCK_EBAY,
            () -> SpringUtils.getBean(LingxingInventorySyncService.class).syncAll()); }
    public void syncGoodcangGrnList() { exec("goodcang_grn_list", "谷仓-入库单", "/inbound_order/get_grn_list", LOCK_EBAY,
            () -> SpringUtils.getBean(GoodcangGrnSyncService.class).syncGrnList(3)); }
    public void syncGoodcangGrnDetail() { exec("goodcang_grn_detail", "谷仓-入库单详情", "/inbound_order/get_grn_detail", LOCK_EBAY,
            () -> SpringUtils.getBean(GoodcangGrnSyncService.class).syncAllGrnDetails()); }
    public void syncLingxingStatement() { exec("warehouse_statement", "领星-库存流水", "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement", LOCK_EBAY,
            () -> SpringUtils.getBean(LingxingStatementSyncService.class).sync()); }
    public void syncLingxingPurchaseOrder() { exec("purchase_order", "领星-采购单", "erp/sc/routing/data/local_inventory/purchaseOrderList", LOCK_EBAY,
            () -> SpringUtils.getBean(LingxingPurchaseOrderSyncService.class).sync()); }
    public void syncLingxingPurchasePlan() { exec("purchase_plan", "领星-采购计划", "erp/sc/routing/data/local_inventory/getPurchasePlans", LOCK_EBAY,
            () -> SpringUtils.getBean(LingxingPurchasePlanSyncService.class).sync()); }

    // ==================== 快照刷新 ====================
    public void refreshEbayReplenishmentSnapshot() { exec("ebay_replenish_snapshot", "刷新eBay补货快照", "compute/ebayReplenishment", LOCK_EBAY,
            () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService.class).refreshSnapshot();
                    return OperationSyncResult.success("ebay_replenish_snapshot", "刷新eBay补货快照", "compute/ebayReplenishment", rows, rows, 0); }); }
    public void refreshEbayPriceTrackingSnapshot() { exec("ebay_price_tracking_snapshot", "刷新eBay跟价表", "compute/ebayPriceTracking", LOCK_EBAY,
            () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayPriceTrackingService.class).refreshSnapshot();
                    return OperationSyncResult.success("ebay_price_tracking_snapshot", "刷新eBay跟价表", "compute/ebayPriceTracking", rows, rows, 0); }); }

    // ==================== Amazon 同步 ====================
    public void syncAmzOrderProfit() { exec("amz_order_profit", "领星-Amazon订单利润", "basicOpen/finance/mreport/OrderProfit", LOCK_AMZ,
            () -> SpringUtils.getBean(AmzOrderProfitSyncService.class).syncAll()); }
    public void syncAmzRestockSummary() { exec("amz_restock_summary", "领星-Amazon补货建议", "erp/sc/routing/restocking/analysis/getSummaryList", LOCK_AMZ,
            () -> SpringUtils.getBean(AmzRestockSummarySyncService.class).syncAll()); }
    public void syncAmzWarehouseInventory() { exec("amz_warehouse_inventory", "领星-Amazon库存明细", "erp/sc/routing/data/local_inventory/inventoryDetails", LOCK_AMZ,
            () -> SpringUtils.getBean(AmzWarehouseInventorySyncService.class).syncAll()); }
    public void refreshAmzReplenishmentSnapshot() { exec("amz_replenish_snapshot", "刷新Amazon补货快照", "compute/amzReplenishment", LOCK_AMZ,
            () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService.class).refreshSnapshot();
                    return OperationSyncResult.success("amz_replenish_snapshot", "刷新Amazon补货快照", "compute/amzReplenishment", rows, rows, 0); }); }

    // ==================== FBA 货件 ====================
    public void syncAmzFbaShipment() { exec("amz_fba_shipment", "领星-FBA货件", "erp/sc/data/fba_report/shipmentList", LOCK_AMZ,
            () -> SpringUtils.getBean(AmzFbaShipmentSyncService.class).sync()); }

    // ==================== 内部方法 ====================
    private static final int TASK_TIMEOUT_MINUTES = 30;
    private static final ExecutorService TIMEOUT_POOL = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "sync-task"); t.setDaemon(true); return t;
    });

    @FunctionalInterface
    private interface SyncRunner { OperationSyncResult run() throws Exception; }

    private void exec(String type, String name, String api, String lockKey, SyncRunner runner) {
        if (lockKey == null) {
            executeWithLog(type, name, api, runner);
            return;
        }

        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        if (!redis.tryLock(LOCK_GLOBAL, LOCK_TIMEOUT_SECONDS)) {
            LOG.info("[SKIP] {} - {} is occupied, skip this schedule", name, LOCK_GLOBAL);
            return;
        }
        if (!redis.tryLock(lockKey, LOCK_TIMEOUT_SECONDS)) {
            redis.unlock(LOCK_GLOBAL);
            LOG.info("[SKIP] {} - {} is occupied, skip this schedule", name, lockKey);
            return;
        }

        try {
            executeWithLog(type, name, api, runner);
        } finally {
            redis.unlock(lockKey);
            redis.unlock(LOCK_GLOBAL);
        }
    }

    private void executeWithLog(String syncType, String syncName, String apiPath, SyncRunner runner) {
        long start = System.currentTimeMillis();
        IOperationSyncLogService logService = SpringUtils.getBean(IOperationSyncLogService.class);
        Long logId = null;
        Future<OperationSyncResult> future = null;
        OperationSyncResult result;
        try {
            logId = logService.start(syncType, syncName, apiPath, "JOB", "SYSTEM", null, null);
            future = TIMEOUT_POOL.submit(() -> {
                OperationSyncResult r = runner.run();
                r.setElapsedMs(System.currentTimeMillis() - start);
                return r;
            });
            result = future.get(TASK_TIMEOUT_MINUTES, TimeUnit.MINUTES);
            logService.finish(logId, result);
        } catch (TimeoutException e) {
            if (future != null) future.cancel(true);
            result = OperationSyncResult.timeout(syncType, syncName, apiPath,
                    "任务执行超时(" + TASK_TIMEOUT_MINUTES + "分钟)，已请求取消后台任务", System.currentTimeMillis() - start);
            LOG.error("同步任务超时 [{}] {}: 超过{}分钟，已请求取消后台任务", syncType, syncName, TASK_TIMEOUT_MINUTES);
            if (logId != null) logService.finish(logId, result);
        } catch (Exception e) {
            LOG.error("同步任务异常 [{}] {}: {}", syncType, syncName, e.getMessage(), e);
            result = OperationSyncResult.failed(syncType, syncName, apiPath, e.getMessage(), System.currentTimeMillis() - start);
            if (logId != null) logService.finish(logId, result);
        }
        OperationSyncContext.set(result);
    }
}
