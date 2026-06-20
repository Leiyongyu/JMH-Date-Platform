package com.ruoyi.web.task;

import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.goodcang.*;
import com.ruoyi.system.service.operation.external.lingxing.*;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 运营数据同步定时任务 Bean —— 供若依 sys_job 定时调度。
 * 定时任务和手动按钮共用同一套同步服务，trigger_type=JOB 区分来源。
 */
@Component("operationSyncTask")
public class OperationSyncTask
{
    private static final Logger LOG = LoggerFactory.getLogger(OperationSyncTask.class);

    // ==================== 低频基础同步 ====================

    /** 1. 谷仓-仓库信息 */
    public void syncGoodcangWarehouse() {
        executeWithLog("goodcang_warehouse", "谷仓-仓库信息", "/base_data/get_warehouse",
                () -> SpringUtils.getBean(GoodcangWarehouseSyncService.class).syncWarehouses());
    }

    /** 2. 领星-仓库信息 */
    public void syncLingxingWarehouse() {
        executeWithLog("warehouse", "领星-仓库信息", "erp/sc/data/local_inventory/warehouse",
                () -> SpringUtils.getBean(LingxingWarehouseSyncService.class).syncWarehouses());
    }

    /** 3. 领星-店铺列表 */
    public void syncLingxingShop() {
        executeWithLog("shop_list", "领星-店铺列表", "pb/mp/shop/v2/getSellerList",
                () -> SpringUtils.getBean(LingxingShopSyncService.class).syncShops());
    }

    /** 4. 领星-eBay商品刊登 */
    public void syncEbayListing() {
        executeWithLog("ebay_listing", "领星-eBay商品刊登", "basicOpen/multiplatform/ebay/list",
                () -> SpringUtils.getBean(LingxingEbaySyncService.class).syncAll());
    }

    /** 5. 谷仓-商品信息 */
    public void syncGoodcangProduct() {
        executeWithLog("goodcang_product", "谷仓-商品信息", "/product/get_product_sku_list",
                () -> SpringUtils.getBean(GoodcangProductSyncService.class).syncFromApi());
    }

    /** 6. 领星-Amazon商品刊登 */
    public void syncAmzListing() {
        executeWithLog("amz_listing", "领星-Amazon商品刊登", "erp/sc/data/mws/listing",
                () -> SpringUtils.getBean(LingxingAmzListingSyncService.class).syncAll());
    }

    // ==================== 每日高频同步 ====================

    /** 7. 领星-库存明细 */
    public void syncLingxingInventory() {
        executeWithLog("lingxing_inventory", "领星-库存明细", "erp/sc/routing/data/local_inventory/inventoryDetails",
                () -> SpringUtils.getBean(LingxingInventorySyncService.class).syncAll());
    }

    /** 8. 谷仓-入库单 */
    public void syncGoodcangGrnList() {
        executeWithLog("goodcang_grn_list", "谷仓-入库单", "/inbound_order/get_grn_list",
                () -> SpringUtils.getBean(GoodcangGrnSyncService.class).syncGrnList(3));
    }

    /** 9. 谷仓-入库单详情 */
    public void syncGoodcangGrnDetail() {
        executeWithLog("goodcang_grn_detail", "谷仓-入库单详情", "/inbound_order/get_grn_detail",
                () -> SpringUtils.getBean(GoodcangGrnSyncService.class).syncAllGrnDetails());
    }

    // ==================== 待实现 ====================

    /** 10. 领星-库存流水 */
    public void syncLingxingStatement() {
        executeWithLog("warehouse_statement", "领星-库存流水", "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement",
                () -> SpringUtils.getBean(LingxingStatementSyncService.class).sync());
    }

    /** 11. 领星-采购单 */
    public void syncLingxingPurchaseOrder() {
        executeWithLog("purchase_order", "领星-采购单", "erp/sc/routing/data/local_inventory/purchaseOrderList",
                () -> SpringUtils.getBean(LingxingPurchaseOrderSyncService.class).sync());
    }

    /** 12. 领星-采购计划 */
    public void syncLingxingPurchasePlan() {
        executeWithLog("purchase_plan", "领星-采购计划", "erp/sc/routing/data/local_inventory/getPurchasePlans",
                () -> SpringUtils.getBean(LingxingPurchasePlanSyncService.class).sync());
    }

    // ==================== 快照刷新 ====================

    /** 13. 刷新eBay补货快照 */
    public void refreshEbayReplenishmentSnapshot() {
        executeWithLog("ebay_replenish_snapshot", "刷新eBay补货快照", "compute/ebayReplenishment",
                () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService.class).refreshSnapshot();
                        return OperationSyncResult.success("ebay_replenish_snapshot", "刷新eBay补货快照", "compute/ebayReplenishment", rows, rows, 0); });
    }

    /** 14. 刷新eBay跟价表 */
    public void refreshEbayPriceTrackingSnapshot() {
        executeWithLog("ebay_price_tracking_snapshot", "刷新eBay跟价表", "compute/ebayPriceTracking",
                () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayPriceTrackingService.class).refreshSnapshot();
                        return OperationSyncResult.success("ebay_price_tracking_snapshot", "刷新eBay跟价表", "compute/ebayPriceTracking", rows, rows, 0); });
    }

    // ==================== Amazon 同步 ====================

    /** 15. 领星-Amazon订单利润 */
    public void syncAmzOrderProfit() {
        executeWithLog("amz_order_profit", "领星-Amazon订单利润", "basicOpen/finance/mreport/OrderProfit",
                () -> SpringUtils.getBean(AmzOrderProfitSyncService.class).syncAll());
    }

    /** 16. 领星-Amazon补货建议 */
    public void syncAmzRestockSummary() {
        executeWithLog("amz_restock_summary", "领星-Amazon补货建议", "erp/sc/routing/restocking/analysis/getSummaryList",
                () -> SpringUtils.getBean(AmzRestockSummarySyncService.class).syncAll());
    }

    /** 17. 领星-Amazon库存明细 */
    public void syncAmzWarehouseInventory() {
        executeWithLog("amz_warehouse_inventory", "领星-Amazon库存明细", "erp/sc/routing/data/local_inventory/inventoryDetails",
                () -> SpringUtils.getBean(AmzWarehouseInventorySyncService.class).syncAll());
    }

    /** 18. 刷新Amazon补货快照 */
    public void refreshAmzReplenishmentSnapshot() {
        executeWithLog("amz_replenish_snapshot", "刷新Amazon补货快照", "compute/amzReplenishment",
                () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService.class).refreshSnapshot();
                        return OperationSyncResult.success("amz_replenish_snapshot", "刷新Amazon补货快照", "compute/amzReplenishment", rows, rows, 0); });
    }

    // ==================== 内部方法 ====================

    private static final int TASK_TIMEOUT_MINUTES = 30;
    private static final java.util.concurrent.ExecutorService TIMEOUT_POOL = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "sync-task"); t.setDaemon(true); return t;
    });

    @FunctionalInterface
    private interface SyncRunner { OperationSyncResult run() throws Exception; }

    private void executeWithLog(String syncType, String syncName, String apiPath, SyncRunner runner) {
        long start = System.currentTimeMillis();
        IOperationSyncLogService logService = SpringUtils.getBean(IOperationSyncLogService.class);
        Long logId = null;
        OperationSyncResult result;
        try {
            logId = logService.start(syncType, syncName, apiPath, "JOB", "SYSTEM", null, null);
            Future<OperationSyncResult> future = TIMEOUT_POOL.submit(() -> {
                OperationSyncResult r = runner.run();
                r.setElapsedMs(System.currentTimeMillis() - start);
                return r;
            });
            result = future.get(TASK_TIMEOUT_MINUTES, TimeUnit.MINUTES);
            logService.finish(logId, result);
        } catch (TimeoutException e) {
            long elapsed = System.currentTimeMillis() - start;
            result = OperationSyncResult.failed(syncType, syncName, apiPath,
                    "任务执行超时(" + TASK_TIMEOUT_MINUTES + "分钟)", elapsed);
            LOG.error("同步任务超时 [{}] {}: 超过{}分钟", syncType, syncName, TASK_TIMEOUT_MINUTES);
            if (logId != null) logService.finish(logId, result);
        } catch (Exception e) {
            LOG.error("同步任务异常 [{}] {}: {}", syncType, syncName, e.getMessage(), e);
            result = OperationSyncResult.failed(syncType, syncName, apiPath, e.getMessage(), System.currentTimeMillis() - start);
            if (logId != null) logService.finish(logId, result);
        }
        OperationSyncContext.set(result);
    }
}
