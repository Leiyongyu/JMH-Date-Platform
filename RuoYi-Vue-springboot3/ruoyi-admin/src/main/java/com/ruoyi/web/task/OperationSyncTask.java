package com.ruoyi.web.task;

import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingShopSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingWarehouseSyncService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 运营数据同步定时任务 Bean —— 供若依 sys_job 定时调度。
 * <p>
 * 放在 ruoyi-admin 模块下以确保可以访问所有业务层的 Spring Bean。
 * <p>
 * 若依定时任务页面调用目标填写格式：
 * <pre>
 *   operationSyncTask.syncGoodcangWarehouse()
 *   operationSyncTask.syncLingxingWarehouse()
 *   operationSyncTask.syncLingxingShop()
 *   operationSyncTask.syncEbayListing()
 *   operationSyncTask.syncGoodcangProduct()
 *   operationSyncTask.syncAmzListing()
 *   operationSyncTask.syncLingxingInventory()
 *   operationSyncTask.syncGoodcangGrnList()
 *   operationSyncTask.syncGoodcangGrnDetail()
 *   operationSyncTask.syncLingxingStatement()
 *   operationSyncTask.syncLingxingPurchaseOrder()
 *   operationSyncTask.syncLingxingPurchasePlan()
 *   operationSyncTask.refreshEbayReplenishmentSnapshot()
 *   operationSyncTask.refreshEbayPriceTrackingSnapshot()
 *   operationSyncTask.syncAmzOrderProfit()
 *   operationSyncTask.syncAmzRestockSummary()
 *   operationSyncTask.syncAmzWarehouseInventory()
 *   operationSyncTask.refreshAmzReplenishmentSnapshot()
 * </pre>
 *
 * @author JMH
 */
@Component("operationSyncTask")
public class OperationSyncTask
{
    private static final Logger LOG = LoggerFactory.getLogger(OperationSyncTask.class);

    // ==================== 低频基础同步（每周一凌晨） ====================

    /** 1. 谷仓-仓库信息 */
    public void syncGoodcangWarehouse()
    {
        executeWithLog("goodcang_warehouse", "谷仓-仓库信息",
                "/base_data/get_warehouse", () -> {
                    LOG.info("syncGoodcangWarehouse - 待实现");
                    return OperationSyncResult.success("goodcang_warehouse", "谷仓-仓库信息",
                            "/base_data/get_warehouse", 0, 0, 0);
                });
    }

    /** 2. 领星-仓库信息 */
    public void syncLingxingWarehouse()
    {
        executeWithLog("warehouse", "领星-仓库信息",
                "erp/sc/data/local_inventory/warehouse", () -> {
                    LingxingWarehouseSyncService svc =
                            SpringUtils.getBean(LingxingWarehouseSyncService.class);
                    return svc.syncWarehouses();
                });
    }

    /** 3. 领星-店铺列表（eBay+Amazon 一次请求） */
    public void syncLingxingShop()
    {
        executeWithLog("shop_list", "领星-店铺列表",
                "pb/mp/shop/v2/getSellerList", () -> {
                    LingxingShopSyncService svc =
                            SpringUtils.getBean(LingxingShopSyncService.class);
                    return svc.syncShops();
                });
    }

    /** 4. 领星-eBay商品刊登 */
    public void syncEbayListing()
    {
        executeWithLog("ebay_listing", "领星-eBay商品刊登",
                "basicOpen/multiplatform/ebay/list", () -> {
                    LOG.info("syncEbayListing - 待实现");
                    return OperationSyncResult.success("ebay_listing", "领星-eBay商品刊登",
                            "basicOpen/multiplatform/ebay/list", 0, 0, 0);
                });
    }

    /** 5. 谷仓-商品信息 */
    public void syncGoodcangProduct()
    {
        executeWithLog("goodcang_product", "谷仓-商品信息",
                "/product/get_product_sku_list", () -> {
                    LOG.info("syncGoodcangProduct - 待实现");
                    return OperationSyncResult.success("goodcang_product", "谷仓-商品信息",
                            "/product/get_product_sku_list", 0, 0, 0);
                });
    }

    /** 6. 领星-Amazon商品刊登 */
    public void syncAmzListing()
    {
        executeWithLog("amz_listing", "领星-Amazon商品刊登",
                "erp/sc/data/mws/listing", () -> {
                    LOG.info("syncAmzListing - 待实现");
                    return OperationSyncResult.success("amz_listing", "领星-Amazon商品刊登",
                            "erp/sc/data/mws/listing", 0, 0, 0);
                });
    }

    // ==================== 每日高频同步 ====================

    /** 7. 领星-库存明细 */
    public void syncLingxingInventory()
    {
        executeWithLog("lingxing_inventory", "领星-库存明细",
                "erp/sc/routing/data/local_inventory/inventoryDetails", () -> {
                    LOG.info("syncLingxingInventory - 待实现");
                    return OperationSyncResult.success("lingxing_inventory", "领星-库存明细",
                            "erp/sc/routing/data/local_inventory/inventoryDetails", 0, 0, 0);
                });
    }

    /** 8. 谷仓-入库单 */
    public void syncGoodcangGrnList()
    {
        executeWithLog("goodcang_grn_list", "谷仓-入库单",
                "/inbound_order/get_grn_list", () -> {
                    LOG.info("syncGoodcangGrnList - 待实现");
                    return OperationSyncResult.success("goodcang_grn_list", "谷仓-入库单",
                            "/inbound_order/get_grn_list", 0, 0, 0);
                });
    }

    /** 9. 谷仓-入库单详情 */
    public void syncGoodcangGrnDetail()
    {
        executeWithLog("goodcang_grn_detail", "谷仓-入库单详情",
                "/inbound_order/get_grn_detail", () -> {
                    LOG.info("syncGoodcangGrnDetail - 待实现");
                    return OperationSyncResult.success("goodcang_grn_detail", "谷仓-入库单详情",
                            "/inbound_order/get_grn_detail", 0, 0, 0);
                });
    }

    /** 10. 领星-库存流水 */
    public void syncLingxingStatement()
    {
        executeWithLog("warehouse_statement", "领星-库存流水",
                "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement", () -> {
                    LOG.info("syncLingxingStatement - 待实现");
                    return OperationSyncResult.success("warehouse_statement", "领星-库存流水",
                            "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement", 0, 0, 0);
                });
    }

    /** 11. 领星-采购单 */
    public void syncLingxingPurchaseOrder()
    {
        executeWithLog("purchase_order", "领星-采购单",
                "erp/sc/routing/data/local_inventory/purchaseOrderList", () -> {
                    LOG.info("syncLingxingPurchaseOrder - 待实现");
                    return OperationSyncResult.success("purchase_order", "领星-采购单",
                            "erp/sc/routing/data/local_inventory/purchaseOrderList", 0, 0, 0);
                });
    }

    /** 12. 领星-采购计划 */
    public void syncLingxingPurchasePlan()
    {
        executeWithLog("purchase_plan", "领星-采购计划",
                "erp/sc/routing/data/local_inventory/getPurchasePlans", () -> {
                    LOG.info("syncLingxingPurchasePlan - 待实现");
                    return OperationSyncResult.success("purchase_plan", "领星-采购计划",
                            "erp/sc/routing/data/local_inventory/getPurchasePlans", 0, 0, 0);
                });
    }

    // ==================== 快照刷新 ====================

    /** 13. 刷新eBay补货快照 */
    public void refreshEbayReplenishmentSnapshot()
    {
        executeWithLog("ebay_replenish_snapshot", "刷新eBay补货快照",
                "compute/ebayReplenishment", () -> {
                    LOG.info("refreshEbayReplenishmentSnapshot - 待实现");
                    return OperationSyncResult.success("ebay_replenish_snapshot", "刷新eBay补货快照",
                            "compute/ebayReplenishment", 0, 0, 0);
                });
    }

    /** 14. 刷新eBay跟价表 */
    public void refreshEbayPriceTrackingSnapshot()
    {
        executeWithLog("ebay_price_tracking_snapshot", "刷新eBay跟价表",
                "compute/ebayPriceTracking", () -> {
                    LOG.info("refreshEbayPriceTrackingSnapshot - 待实现");
                    return OperationSyncResult.success("ebay_price_tracking_snapshot", "刷新eBay跟价表",
                            "compute/ebayPriceTracking", 0, 0, 0);
                });
    }

    // ==================== Amazon 同步 ====================

    /** 15. 领星-Amazon订单利润 */
    public void syncAmzOrderProfit()
    {
        executeWithLog("amz_order_profit", "领星-Amazon订单利润",
                "basicOpen/finance/mreport/OrderProfit", () -> {
                    LOG.info("syncAmzOrderProfit - 待实现");
                    return OperationSyncResult.success("amz_order_profit", "领星-Amazon订单利润",
                            "basicOpen/finance/mreport/OrderProfit", 0, 0, 0);
                });
    }

    /** 16. 领星-Amazon补货建议 */
    public void syncAmzRestockSummary()
    {
        executeWithLog("amz_restock_summary", "领星-Amazon补货建议",
                "erp/sc/routing/restocking/analysis/getSummaryList", () -> {
                    LOG.info("syncAmzRestockSummary - 待实现");
                    return OperationSyncResult.success("amz_restock_summary", "领星-Amazon补货建议",
                            "erp/sc/routing/restocking/analysis/getSummaryList", 0, 0, 0);
                });
    }

    /** 17. 领星-Amazon库存明细 */
    public void syncAmzWarehouseInventory()
    {
        executeWithLog("amz_warehouse_inventory", "领星-Amazon库存明细",
                "erp/sc/routing/data/local_inventory/inventoryDetails", () -> {
                    LOG.info("syncAmzWarehouseInventory - 待实现");
                    return OperationSyncResult.success("amz_warehouse_inventory", "领星-Amazon库存明细",
                            "erp/sc/routing/data/local_inventory/inventoryDetails", 0, 0, 0);
                });
    }

    /** 18. 刷新Amazon补货快照 */
    public void refreshAmzReplenishmentSnapshot()
    {
        executeWithLog("amz_replenish_snapshot", "刷新Amazon补货快照",
                "compute/amzReplenishment", () -> {
                    LOG.info("refreshAmzReplenishmentSnapshot - 待实现");
                    return OperationSyncResult.success("amz_replenish_snapshot", "刷新Amazon补货快照",
                            "compute/amzReplenishment", 0, 0, 0);
                });
    }

    // ==================== 内部框架方法 ====================

    @FunctionalInterface
    private interface SyncRunner
    {
        OperationSyncResult run() throws Exception;
    }

    /**
     * 统一同步执行模板：写日志 → 执行 → 更新日志 → 写入 ThreadLocal 供 AbstractQuartzJob 读取。
     */
    private void executeWithLog(String syncType, String syncName, String apiPath,
                                 SyncRunner runner)
    {
        long start = System.currentTimeMillis();
        IOperationSyncLogService logService = SpringUtils.getBean(IOperationSyncLogService.class);
        Long logId = null;
        OperationSyncResult result;

        try
        {
            logId = logService.start(syncType, syncName, apiPath, "JOB", "SYSTEM", null, null);
            result = runner.run();
            result.setElapsedMs(System.currentTimeMillis() - start);
            logService.finish(logId, result);
        }
        catch (Exception e)
        {
            LOG.error("同步任务执行异常 [{}] {}: {}", syncType, syncName, e.getMessage(), e);
            long elapsed = System.currentTimeMillis() - start;
            result = OperationSyncResult.failed(syncType, syncName, apiPath,
                    e.getMessage(), elapsed);
            if (logId != null)
            {
                logService.finish(logId, result);
            }
        }

        OperationSyncContext.set(result);
    }
}
