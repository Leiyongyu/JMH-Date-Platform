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

/**
 * eBay 统一同步服务 —— 按固定顺序拉取源数据并刷新补货/跟价两张快照。
 * <p>
 * 流程：店铺 → 仓库 → eBay Listing → 库存明细 → 谷仓仓库 → 谷仓商品
 * → 谷仓入库单 → 入库单详情 → 库存流水 → eBay补货快照 → eBay跟价快照
 *
 * @author JMH
 */
@Service
public class EbayUnifiedSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(EbayUnifiedSyncService.class);

    /** 11 步，定义顺序和名称 */
    private static final StepDef[] STEPS = {
        new StepDef("shop_list",        "领星-店铺列表",        "pb/mp/shop/v2/getSellerList"),
        new StepDef("warehouse",        "领星-仓库信息",        "erp/sc/data/local_inventory/warehouse", true),
        new StepDef("ebay_listing",     "领星-eBay商品刊登",    "basicOpen/multiplatform/ebay/list"),
        new StepDef("lingxing_inv",     "领星-库存明细",        "erp/sc/routing/data/local_inventory/inventoryDetails"),
        new StepDef("gc_warehouse",     "谷仓-仓库信息",        "/base_data/get_warehouse"),
        new StepDef("gc_product",       "谷仓-商品信息",        "/product/get_product_sku_list"),
        new StepDef("gc_grn_list",      "谷仓-入库单",          "/inbound_order/get_grn_list"),
        new StepDef("gc_grn_detail",    "谷仓-入库单详情",      "/inbound_order/get_grn_detail"),
        new StepDef("statement",        "领星-库存流水",        "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement"),
        new StepDef("ebay_replenish",   "刷新eBay补货快照",     "compute/ebayReplenishment"),
        new StepDef("ebay_tracking",    "刷新eBay跟价快照",     "compute/ebayPriceTracking"),
    };

    /** 仅刷新快照（不拉源数据） */
    private static final StepDef[] REFRESH_ONLY_STEPS = {
        new StepDef("ebay_replenish", "刷新eBay补货快照", "compute/ebayReplenishment"),
        new StepDef("ebay_tracking",  "刷新eBay跟价快照", "compute/ebayPriceTracking"),
    };

    /**
     * 全量同步：拉源数据 + 刷新快照。
     * @return Map 包含 parentLogId, steps, totalStatus
     */
    public Map<String, Object> syncAll(String triggerType, String operator)
    {
        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        if (!redis.tryLock("lock:sync:ebay", 600))
        {
            Map<String, Object> busy = new LinkedHashMap<>();
            busy.put("parentStatus", "BUSY"); busy.put("msg", "eBay数据同步正在执行中，请稍后再试");
            return busy;
        }
        try { return executeSteps(STEPS, "eBay-手动拉取最新数据", triggerType, operator); }
        finally { redis.unlock("lock:sync:ebay"); }
    }

    public Map<String, Object> refreshOnly(String triggerType, String operator)
    {
        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        if (!redis.tryLock("lock:sync:ebay", 300))
        {
            Map<String, Object> busy = new LinkedHashMap<>();
            busy.put("parentStatus", "BUSY"); busy.put("msg", "eBay快照刷新正在执行中，请稍后再试");
            return busy;
        }
        try { return executeSteps(REFRESH_ONLY_STEPS, "eBay-仅刷新快照", triggerType, operator); }
        finally { redis.unlock("lock:sync:ebay"); }
    }

    // ==================== 内部执行引擎 ====================

    private Map<String, Object> executeSteps(StepDef[] steps, String parentName,
                                              String triggerType, String operator)
    {
        long totalStart = System.currentTimeMillis();
        IOperationSyncLogService logSvc = SpringUtils.getBean(IOperationSyncLogService.class);

        // 写父日志
        Long parentId = logSvc.start("ebay_manual_sync", parentName, "", triggerType, operator, null, null);

        List<Map<String, Object>> stepResults = new ArrayList<>();
        int successSteps = 0, failedSteps = 0;
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

            OperationSyncResult result;
            try
            {
                result = executeStep(step);
                result.setElapsedMs(System.currentTimeMillis() - stepStart);
                logSvc.finish(childId, result);

                if ("FAILED".equals(result.getStatus()))
                {
                    failedSteps++;
                    if (step.critical) criticalFailed = true;
                    stepResults.add(stepMap(step.key, step.name, "FAILED", result.getErrorMessage()));
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

        // 更新父日志
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

    /** 分发到具体服务实现 */
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
                SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService.class).refreshSnapshot();
                return OperationSyncResult.success("ebay_replenish", "刷新eBay补货快照", "compute/ebayReplenishment", 1, 1, 0);
            case "ebay_tracking":
                SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayPriceTrackingService.class).refreshSnapshot();
                return OperationSyncResult.success("ebay_tracking", "刷新eBay跟价快照", "compute/ebayPriceTracking", 1, 1, 0);
            default:
                LOG.info("eBay步骤 [{}] - 待实现", step.name);
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
        final boolean critical; // 失败是否阻断后续

        StepDef(String key, String name, String apiPath) { this(key, name, apiPath, false); }
        StepDef(String key, String name, String apiPath, boolean critical)
        {
            this.key = key; this.name = name; this.apiPath = apiPath; this.critical = critical;
        }
    }
}
