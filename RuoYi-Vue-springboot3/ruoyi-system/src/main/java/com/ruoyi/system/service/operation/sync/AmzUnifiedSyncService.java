package com.ruoyi.system.service.operation.sync;

import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Amazon 统一同步服务 —— 按固定顺序拉取源数据并刷新 AMZ 补货快照。
 * <p>
 * 流程：店铺 → AMZ Listing → 订单利润 → 补货建议 → 库存明细 → AMZ补货快照
 *
 * @author JMH
 */
@Service
public class AmzUnifiedSyncService
{
    private static final Logger LOG = LoggerFactory.getLogger(AmzUnifiedSyncService.class);

    private static final StepDef[] STEPS = {
        new StepDef("shop_list",          "领星-店铺列表",           "pb/mp/shop/v2/getSellerList"),
        new StepDef("amz_listing",        "领星-Amazon商品刊登",     "erp/sc/data/mws/listing", true),
        new StepDef("amz_profit",         "领星-Amazon订单利润",     "basicOpen/finance/mreport/OrderProfit"),
        new StepDef("amz_restock",        "领星-Amazon补货建议",     "erp/sc/routing/restocking/analysis/getSummaryList"),
        new StepDef("amz_inv",            "领星-Amazon库存明细",     "erp/sc/routing/data/local_inventory/inventoryDetails"),
        new StepDef("amz_replenish",      "刷新Amazon补货快照",      "compute/amzReplenishment"),
    };

    private static final StepDef[] REFRESH_ONLY_STEPS = {
        new StepDef("amz_replenish", "刷新Amazon补货快照", "compute/amzReplenishment"),
    };

    public Map<String, Object> syncAll(String triggerType, String operator)
    {
        return executeSteps(STEPS, "AMZ-手动拉取最新数据", triggerType, operator);
    }

    public Map<String, Object> refreshOnly(String triggerType, String operator)
    {
        return executeSteps(REFRESH_ONLY_STEPS, "AMZ-仅刷新快照", triggerType, operator);
    }

    // ==================== 内部执行引擎 ====================

    private Map<String, Object> executeSteps(StepDef[] steps, String parentName,
                                              String triggerType, String operator)
    {
        long totalStart = System.currentTimeMillis();
        IOperationSyncLogService logSvc = SpringUtils.getBean(IOperationSyncLogService.class);

        Long parentId = logSvc.start("amz_manual_sync", parentName, "", triggerType, operator, null, null);

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
            Long childId = logSvc.start("amz_manual_sync." + step.key, step.name, step.apiPath,
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
                LOG.error("AMZ同步步骤 [{}] 异常: {}", step.name, e.getMessage(), e);
                failedSteps++;
                if (step.critical) criticalFailed = true;
                OperationSyncResult failResult = OperationSyncResult.failed(
                        "amz_manual_sync." + step.key, step.name, step.apiPath,
                        e.getMessage(), System.currentTimeMillis() - stepStart);
                logSvc.finish(childId, failResult);
                stepResults.add(stepMap(step.key, step.name, "FAILED", e.getMessage()));
            }
        }

        long totalElapsed = System.currentTimeMillis() - totalStart;
        String parentStatus = failedSteps == 0 ? "SUCCESS"
                : (successSteps > 0 ? "PARTIAL_SUCCESS" : "FAILED");
        OperationSyncResult parentResult = new OperationSyncResult();
        parentResult.setSyncType("amz_manual_sync");
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
        LOG.info("AMZ步骤 [{}] - 待实现", step.name);
        return OperationSyncResult.success(step.key, step.name, step.apiPath, 0, 0, 0);
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
        final String key; final String name; final String apiPath; final boolean critical;
        StepDef(String key, String name, String apiPath) { this(key, name, apiPath, false); }
        StepDef(String key, String name, String apiPath, boolean critical)
        { this.key = key; this.name = name; this.apiPath = apiPath; this.critical = critical; }
    }
}
