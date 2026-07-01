package com.ruoyi.system.service.operation.sync;

import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangGrnSyncService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangProductSyncService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangWarehouseSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingEbaySyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingInventorySyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingShopSyncService;
import com.ruoyi.system.service.operation.external.lingxing.LingxingWarehouseSyncService;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class EbayUnifiedSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(EbayUnifiedSyncService.class);
    private static final String LOCK_EBAY = "lock:sync:lingxing:ebay";
    private static final int LOCK_TIMEOUT_SECONDS = 2700;

    private static final StepDef[] STEPS = {
        new StepDef("shop_list", "领星-店铺列表", "pb/mp/shop/v2/getSellerList"),
        new StepDef("warehouse", "领星-仓库信息", "erp/sc/data/local_inventory/warehouse", true),
        new StepDef("ebay_listing", "领星-eBay商品刊登", "basicOpen/multiplatform/ebay/list"),
        new StepDef("lingxing_inv", "领星-库存明细", "erp/sc/routing/data/local_inventory/inventoryDetails"),
        new StepDef("gc_warehouse", "谷仓-仓库信息", "/base_data/get_warehouse"),
        new StepDef("gc_product", "谷仓-商品信息", "/product/get_product_sku_list"),
        new StepDef("gc_grn_list", "谷仓-入库单", "/inbound_order/get_grn_list"),
        new StepDef("gc_grn_detail", "谷仓-入库单详情", "/inbound_order/get_grn_detail"),
        new StepDef("statement", "领星-库存流水", "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement"),
        new StepDef("ebay_replenish", "刷新eBay补货快照", "compute/ebayReplenishment"),
        new StepDef("ebay_tracking", "刷新eBay跟价快照", "compute/ebayPriceTracking")
    };

    private static final StepDef[] REFRESH_ONLY_STEPS = {
        new StepDef("ebay_replenish", "刷新eBay补货快照", "compute/ebayReplenishment"),
        new StepDef("ebay_tracking", "刷新eBay跟价快照", "compute/ebayPriceTracking")
    };

    public Map<String, Object> syncAll(String triggerType, String operator)
    {
        return withLock(STEPS, "eBay-手动拉取最新数据", triggerType, operator,
                "eBay数据同步正在执行中，请稍后再试");
    }

    public Map<String, Object> refreshOnly(String triggerType, String operator)
    {
        return withLock(REFRESH_ONLY_STEPS, "eBay-仅刷新快照", triggerType, operator,
                "eBay快照刷新正在执行中，请稍后再试");
    }

    private Map<String, Object> withLock(StepDef[] steps, String parentName, String triggerType,
                                         String operator, String busyMessage)
    {
        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        if (!redis.tryLock(LOCK_EBAY, LOCK_TIMEOUT_SECONDS))
        {
            Map<String, Object> busy = new LinkedHashMap<>();
            busy.put("parentStatus", "BUSY");
            busy.put("msg", busyMessage);
            return busy;
        }
        try
        {
            return executeSteps(steps, parentName, triggerType, operator);
        }
        finally
        {
            redis.unlock(LOCK_EBAY);
        }
    }

    private Map<String, Object> executeSteps(StepDef[] steps, String parentName,
                                             String triggerType, String operator)
    {
        long totalStart = System.currentTimeMillis();
        IOperationSyncLogService logSvc = SpringUtils.getBean(IOperationSyncLogService.class);
        Long parentId = logSvc.start("ebay_manual_sync", parentName, "", triggerType, operator, null, null);

        List<Map<String, Object>> stepResults = new ArrayList<>();
        int successSteps = 0;
        int failedSteps = 0;
        boolean criticalFailed = false;

        for (StepDef step : steps)
        {
            if (criticalFailed)
            {
                stepResults.add(stepMap(step.key, step.name, "SKIPPED", "前置关键步骤失败，跳过"));
                continue;
            }

            long stepStart = System.currentTimeMillis();
            Long childId = logSvc.start("ebay_manual_sync." + step.key, step.name, step.apiPath,
                    triggerType, operator, null, null, parentId);

            try
            {
                OperationSyncResult result = executeStep(step);
                result.setElapsedMs(System.currentTimeMillis() - stepStart);
                logSvc.finish(childId, result);

                if (!OperationSyncResult.STATUS_SUCCESS.equals(result.getStatus()))
                {
                    failedSteps++;
                    if (step.critical) criticalFailed = true;
                    stepResults.add(stepMap(step.key, step.name, result.getStatus(), result.getErrorMessage()));
                }
                else
                {
                    successSteps++;
                    stepResults.add(stepMap(step.key, step.name, "SUCCESS",
                            "总数" + result.getTotalCount() + " 成功" + result.getSuccessCount()
                                    + " 失败" + result.getFailCount()));
                }
            }
            catch (Exception e)
            {
                LOG.error("eBay同步步骤 [{}] 异常: {}", step.name, e.getMessage(), e);
                failedSteps++;
                if (step.critical) criticalFailed = true;
                OperationSyncResult failResult = OperationSyncResult.failed(
                        "ebay_manual_sync." + step.key, step.name, step.apiPath,
                        e.getMessage(), System.currentTimeMillis() - stepStart);
                logSvc.finish(childId, failResult);
                stepResults.add(stepMap(step.key, step.name, "FAILED", e.getMessage()));
            }
        }

        long totalElapsed = System.currentTimeMillis() - totalStart;
        String parentStatus = failedSteps == 0 ? "SUCCESS"
                : (successSteps > 0 ? "PARTIAL_SUCCESS" : "FAILED");
        OperationSyncResult parentResult = new OperationSyncResult();
        parentResult.setSyncType("ebay_manual_sync");
        parentResult.setSyncName(parentName);
        parentResult.setStatus(parentStatus);
        parentResult.setTotalCount(steps.length);
        parentResult.setSuccessCount(successSteps);
        parentResult.setFailCount(failedSteps);
        parentResult.setElapsedMs(totalElapsed);
        logSvc.finish(parentId, parentResult);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("parentLogId", parentId);
        response.put("parentStatus", parentStatus);
        response.put("totalSteps", steps.length);
        response.put("successSteps", successSteps);
        response.put("failedSteps", failedSteps);
        response.put("elapsed", totalElapsed / 1000.0 + "s");
        response.put("steps", stepResults);
        return response;
    }

    private OperationSyncResult executeStep(StepDef step) throws Exception
    {
        switch (step.key)
        {
            case "shop_list":
                return SpringUtils.getBean(LingxingShopSyncService.class).syncShops();
            case "warehouse":
                return SpringUtils.getBean(LingxingWarehouseSyncService.class).syncWarehouses();
            case "ebay_listing":
                return SpringUtils.getBean(LingxingEbaySyncService.class).syncAll();
            case "lingxing_inv":
                return SpringUtils.getBean(LingxingInventorySyncService.class).syncAll();
            case "gc_warehouse":
                return SpringUtils.getBean(GoodcangWarehouseSyncService.class).syncWarehouses();
            case "gc_product":
                return SpringUtils.getBean(GoodcangProductSyncService.class).syncFromApi();
            case "gc_grn_list":
                return SpringUtils.getBean(GoodcangGrnSyncService.class).syncGrnList(3);
            case "gc_grn_detail":
                return SpringUtils.getBean(GoodcangGrnSyncService.class).syncAllGrnDetails();
            case "statement":
                return SpringUtils.getBean(com.ruoyi.system.service.operation.external.lingxing.LingxingStatementSyncService.class).sync();
            case "ebay_replenish":
                int replenishRows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService.class)
                        .refreshSnapshot();
                return OperationSyncResult.success("ebay_replenish", "刷新eBay补货快照",
                        "compute/ebayReplenishment", replenishRows, replenishRows, 0);
            case "ebay_tracking":
                int trackingRows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayPriceTrackingService.class)
                        .refreshSnapshot();
                return OperationSyncResult.success("ebay_tracking", "刷新eBay跟价快照",
                        "compute/ebayPriceTracking", trackingRows, trackingRows, 0);
            default:
                LOG.info("eBay步骤 [{}] 未实现", step.name);
                return OperationSyncResult.success(step.key, step.name, step.apiPath, 0, 0, 0);
        }
    }

    private Map<String, Object> stepMap(String key, String name, String status, String message)
    {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("key", key);
        m.put("name", name);
        m.put("status", status);
        m.put("message", message);
        return m;
    }

    private static class StepDef
    {
        final String key;
        final String name;
        final String apiPath;
        final boolean critical;

        StepDef(String key, String name, String apiPath)
        {
            this(key, name, apiPath, false);
        }

        StepDef(String key, String name, String apiPath, boolean critical)
        {
            this.key = key;
            this.name = name;
            this.apiPath = apiPath;
            this.critical = critical;
        }
    }
}
