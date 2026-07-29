package com.ruoyi.system.service.operation.sync;

import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.common.utils.spring.SpringUtils;
import com.ruoyi.system.mapper.operation.external.AmzFbaShipmentMapper;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangGrnSyncService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangProductSyncService;
import com.ruoyi.system.service.operation.external.goodcang.GoodcangWarehouseSyncService;
import com.ruoyi.system.service.operation.external.lingxing.*;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.*;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

/**
 * 同步链路编排器 —— 按预定义链路顺序执行多个同步步骤。
 * <p>
 * 每条链路有独立的 Redis 锁，每步也有独立的步骤锁；
 * 领星 API 步骤受全局限流（最多 2 个并发）。
 */
@Service
public class SyncOrchestratorService
{
    private static final Logger LOG = LoggerFactory.getLogger(SyncOrchestratorService.class);

    /** 领星 API 全局并发限流 */
    static final Semaphore LINGXING_SEM = new Semaphore(2);

    private static final int CHAIN_LOCK_TTL = 4500;
    private static final int STEP_LOCK_TTL = 3600;
    private static final int STEP_TIMEOUT_MINUTES = 60;
    private static final int STEP_MAX_ATTEMPTS = 2;
    private static final int STEP_RETRY_DELAY_SECONDS = 10;

    private final ThreadPoolTaskExecutor executor;

    public SyncOrchestratorService()
    {
        executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("chain-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
    }

    @PreDestroy
    public void shutdown()
    {
        executor.shutdown();
    }

    // ==================== 步骤定义 ====================

    @FunctionalInterface
    interface SyncRunner { OperationSyncResult run() throws Exception; }

    static class StepDef
    {
        final String code, name, apiPath;
        final boolean required, zeroAllowed, usesLingxing;
        final SyncRunner runner;

        StepDef(String code, String name, String apiPath, boolean required,
                boolean zeroAllowed, boolean usesLingxing, SyncRunner runner)
        {
            this.code = code; this.name = name; this.apiPath = apiPath;
            this.required = required; this.zeroAllowed = zeroAllowed;
            this.usesLingxing = usesLingxing; this.runner = runner;
        }
    }

    // ==================== 7 条链路 ====================

    enum Chain
    {
        BASE("base", "基础数据同步", Arrays.asList(
            new StepDef("shop_list", "领星-店铺列表", "pb/mp/shop/v2/getSellerList",
                true, false, true,
                () -> SpringUtils.getBean(LingxingShopSyncService.class).syncShops()),
            new StepDef("warehouse", "领星-仓库信息", "erp/sc/data/local_inventory/warehouse",
                true, false, true,
                () -> SpringUtils.getBean(LingxingWarehouseSyncService.class).syncWarehouses()),
            new StepDef("product_weight", "领星-产品管理", "erp/sc/routing/data/local_inventory/productInfo",
                false, true, true,
                () -> SpringUtils.getBean(LingxingProductWeightSyncService.class).sync())
        )),
        EBAY("ebay", "eBay数据同步", Arrays.asList(
            new StepDef("ebay_listing", "领星-eBay商品刊登", "basicOpen/multiplatform/ebay/list",
                true, false, true,
                () -> SpringUtils.getBean(LingxingEbaySyncService.class).syncAll()),
            new StepDef("lingxing_inventory", "领星-库存明细", "erp/sc/routing/data/local_inventory/inventoryDetails",
                false, false, true,
                () -> SpringUtils.getBean(LingxingInventorySyncService.class).syncAll()),
            new StepDef("statement", "领星-库存流水", "erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement",
                false, false, true,
                () -> SpringUtils.getBean(LingxingStatementSyncService.class).sync()),
            new StepDef("ebay_replenish", "刷新eBay补货快照", "compute/ebayReplenishment",
                false, true, false,
                () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayReplenishmentSnapshotService.class).refreshSnapshot();
                        return OperationSyncResult.success("ebay_replenish", "刷新eBay补货快照", "compute/ebayReplenishment", rows, rows, 0); }),
            new StepDef("ebay_tracking", "刷新eBay跟价快照", "compute/ebayPriceTracking",
                false, true, false,
                () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IEbayPriceTrackingService.class).refreshSnapshot();
                        return OperationSyncResult.success("ebay_tracking", "刷新eBay跟价快照", "compute/ebayPriceTracking", rows, rows, 0); })
        )),
        AMZ("amz", "AMZ补货数据同步", Arrays.asList(
            new StepDef("amz_listing", "领星-Amazon商品刊登", "erp/sc/data/mws/listing",
                true, false, true,
                () -> SpringUtils.getBean(LingxingAmzListingSyncService.class).syncAll()),
            new StepDef("amz_profit", "领星-Amazon订单利润", "basicOpen/finance/mreport/OrderProfit",
                false, false, true,
                () -> SpringUtils.getBean(AmzOrderProfitSyncService.class).syncAll()),
            new StepDef("amz_profit_90d", "领星-Amazon最近90天利润率", "basicOpen/finance/mreport/OrderProfit",
                false, false, true,
                () -> SpringUtils.getBean(AmzOrderProfit90dSyncService.class).syncAll()),
            new StepDef("amz_restock", "领星-Amazon补货建议", "erp/sc/routing/restocking/analysis/getSummaryList",
                false, false, true,
                () -> SpringUtils.getBean(AmzRestockSummarySyncService.class).syncAll()),
            new StepDef("amz_product_inventory", "领星-Amazon产品表现库存", "bd/productPerformance/openApi/asinList",
                true, false, true,
                () -> SpringUtils.getBean(AmzProductPerformanceInventorySyncService.class).syncAll()),
            new StepDef("amz_warehouse_inventory", "领星-Amazon库存明细", "erp/sc/routing/data/local_inventory/inventoryDetails",
                false, false, true,
                () -> SpringUtils.getBean(AmzWarehouseInventorySyncService.class).syncAll()),
            new StepDef("amz_replenish", "刷新Amazon补货快照", "compute/amzReplenishment",
                false, true, false,
                () -> { int rows = SpringUtils.getBean(com.ruoyi.system.service.operation.IAmzReplenishmentSnapshotService.class).refreshSnapshot();
                        return OperationSyncResult.success("amz_replenish", "刷新Amazon补货快照", "compute/amzReplenishment", rows, rows, 0); })
        )),
        FBA("fba", "FBA货件数据同步", Arrays.asList(
            new StepDef("amz_fba_shipment", "领星-FBA货件", "erp/sc/data/fba_report/shipmentList",
                true, false, true,
                () -> SpringUtils.getBean(AmzFbaShipmentSyncService.class).sync()),
            new StepDef("amz_fba_box", "领星-FBA装箱信息", "erp/sc/routing/fba/shipment/boxInfo",
                false, false, true,
                () -> SpringUtils.getBean(AmzFbaShipmentBoxSyncService.class).sync())
        )),
        STOCK_ORDER("stock_order", "备货单数据同步", Arrays.asList(
            new StepDef("stock_order", "领星-备货单号", "erp/sc/routing/owms/inbound/listInbound",
                true, false, true,
                () -> SpringUtils.getBean(OverseasStockOrderSyncService.class).sync()),
            new StepDef("stock_order_detail", "领星-备货单详情", "basicOpen/overSeaWarehouse/stockOrder/detail",
                false, false, true,
                () -> SpringUtils.getBean(OverseasStockOrderDetailSyncService.class).sync())
        )),
        STA_SHIPMENT("sta_shipment", "STA发货链路", Arrays.asList(
            new StepDef("lingxing_shipment_order_mapping", "领星-货件与发货单映射",
                "erp/sc/routing/storage/shipment/getInboundShipmentList",
                true, false, true,
                () -> SpringUtils.getBean(
                        LingxingShipmentOrderMappingSyncService.class).syncAll()),
            new StepDef("lingxing_sta_inbound_plan", "领星-STA任务列表",
                "amzStaServer/openapi/inbound-plan/page",
                true, true, true,
                () -> {
                    Map<String, Object> result = SpringUtils
                            .getBean(LingxingStaInboundPlanSyncService.class).syncAuto();
                    int total = ((Number) result.getOrDefault("remoteTotal", 0L)).intValue();
                    int saved = ((Number) result.getOrDefault("savedPlans", 0)).intValue();
                    long elapsed = ((Number) result.getOrDefault("durationMs", 0L)).longValue();
                    return OperationSyncResult.successAllowEmpty(
                            "lingxing_sta_inbound_plan", "领星-STA任务列表",
                            "amzStaServer/openapi/inbound-plan/page", total, saved, elapsed);
                })
        )),
        GOODCANG("goodcang", "谷仓数据同步", Arrays.asList(
            new StepDef("gc_warehouse", "谷仓-仓库信息", "/base_data/get_warehouse",
                true, false, false,
                () -> SpringUtils.getBean(GoodcangWarehouseSyncService.class).syncWarehouses()),
            new StepDef("gc_product", "谷仓-商品信息", "/product/get_product_sku_list",
                false, false, false,
                () -> SpringUtils.getBean(GoodcangProductSyncService.class).syncFromApi()),
            new StepDef("gc_grn_list", "谷仓-入库单", "/inbound_order/get_grn_list",
                false, false, false,
                () -> SpringUtils.getBean(GoodcangGrnSyncService.class).syncGrnListSmart()),
            new StepDef("gc_grn_detail", "谷仓-入库单详情", "/inbound_order/get_grn_detail",
                false, false, false,
                () -> SpringUtils.getBean(GoodcangGrnSyncService.class).syncAllGrnDetails())
        ));

        final String code, name;
        final List<StepDef> steps;

        Chain(String code, String name, List<StepDef> steps)
        { this.code = code; this.name = name; this.steps = steps; }
    }

    // ==================== 公开入口 ====================

    public void execute(String chainCode)
    {
        Chain chain;
        try { chain = Chain.valueOf(chainCode.toUpperCase()); }
        catch (IllegalArgumentException e) { LOG.error("未知链路: {}", chainCode); return; }
        executeChain(chain);
    }

    // ==================== 核心编排 ====================

    private void executeChain(Chain chain)
    {
        RedisCache redis = SpringUtils.getBean(RedisCache.class);
        String chainLock = "lock:sync:chain:" + chain.code;

        if (!redis.tryLock(chainLock, CHAIN_LOCK_TTL))
        { LOG.info("[SKIP] 链路 {} 执行中，跳过", chain.name); return; }

        long start = System.currentTimeMillis();
        IOperationSyncLogService logSvc = SpringUtils.getBean(IOperationSyncLogService.class);
        Long parentId = logSvc.start("chain:" + chain.code, chain.name, "", "JOB", "SYSTEM", null, null);
        int success = 0, failed = 0;
        boolean criticalFailed = false;
        List<OperationSyncResult.FailureItem> failureItems = new ArrayList<>();

        try
        {
            for (StepDef step : chain.steps)
            {
                if (criticalFailed)
                { LOG.info("[SKIP] 链路 {} 步骤 {} 前置关键步骤失败", chain.name, step.name); continue; }

                String stepLock = "lock:sync:step:" + step.code;
                boolean stepLocked = false, semAcquired = false;
                Long childId = null;
                long stepStart = System.currentTimeMillis();

                try
                {
                    if (!redis.tryLock(stepLock, STEP_LOCK_TTL))
                    { LOG.info("[SKIP] 步骤 {} 执行中", step.name); continue; }
                    stepLocked = true;

                    if (step.usesLingxing) { LINGXING_SEM.acquire(); semAcquired = true; }

                    childId = logSvc.start("chain:" + chain.code + ":" + step.code,
                            step.name, step.apiPath, "JOB", "SYSTEM", null, null, parentId);
                    final Long fChildId = childId;

                    OperationSyncResult r = executeStepWithRetry(chain, step, stepStart);

                    logSvc.finish(fChildId, r);

                    boolean ok = OperationSyncResult.STATUS_SUCCESS.equals(r.getStatus())
                            || OperationSyncResult.STATUS_SKIPPED.equals(r.getStatus());
                    if (!ok)
                    {
                        failed++;
                        if (step.required) criticalFailed = true;
                        String detail = buildStepFailureDetail(chain, step, r, fChildId);
                        failureItems.add(new OperationSyncResult.FailureItem(step.code + " / " + step.name, detail));
                        LOG.warn("链路 {} 步骤 {} 失败: {}", chain.name, step.name, detail);
                        trySendAlert(chain.code, step.code, step.name, step.apiPath, r.getStatus(), detail, fChildId);
                    }
                    else { success++; trySendRecovery(chain.code, step.code, step.name, fChildId); }
                }
                catch (Exception e)
                {
                    LOG.error("链路 {} 步骤 {} 异常: {}", chain.name, step.name, e.getMessage(), e);
                    failed++;
                    if (step.required) criticalFailed = true;
                    String error = rootMessage(e);
                    OperationSyncResult fr = OperationSyncResult.failed("chain:" + chain.code + ":" + step.code,
                            step.name, step.apiPath, error, System.currentTimeMillis() - stepStart);
                    if (childId != null) logSvc.finish(childId, fr);
                    String detail = buildStepFailureDetail(chain, step, fr, childId);
                    failureItems.add(new OperationSyncResult.FailureItem(step.code + " / " + step.name, detail));
                    trySendAlert(chain.code, step.code, step.name, step.apiPath, fr.getStatus(), detail, childId);
                }
                finally
                {
                    if (semAcquired) LINGXING_SEM.release();
                    if (stepLocked) redis.unlock(stepLock);
                }
            }

            long elapsed = System.currentTimeMillis() - start;
            String ps = failed == 0 ? OperationSyncResult.STATUS_SUCCESS
                    : OperationSyncResult.STATUS_FAILED;
            OperationSyncResult pr = new OperationSyncResult();
            pr.setSyncType("chain:" + chain.code); pr.setSyncName(chain.name); pr.setStatus(ps);
            pr.setTotalCount(chain.steps.size()); pr.setSuccessCount(success); pr.setFailCount(failed); pr.setElapsedMs(elapsed);
            pr.setFailures(failureItems);
            if (!failureItems.isEmpty())
            {
                pr.setErrorMessage(failureItems.get(0).getReason());
            }
            logSvc.finish(parentId, pr);
            OperationSyncContext.set(pr);
            LOG.info("链路 {} 完成: {}成功 {}失败 耗时{}s", chain.name, success, failed, elapsed / 1000.0);
        }
        catch (Exception e)
        {
            LOG.error("链路 {} 异常: {}", chain.name, e.getMessage(), e);
            OperationSyncResult failedResult = OperationSyncResult.failed("chain:" + chain.code, chain.name, "",
                    rootMessage(e), System.currentTimeMillis() - start);
            OperationSyncContext.set(failedResult);
            if (parentId != null) logSvc.finish(parentId, failedResult);
        }
        finally { redis.unlock(chainLock); }
    }

    // ==================== FBA 装箱特殊处理 ====================

    private OperationSyncResult executeStepWithRetry(Chain chain, StepDef step, long stepStart)
            throws InterruptedException
    {
        OperationSyncResult last = null;
        for (int attempt = 1; attempt <= STEP_MAX_ATTEMPTS; attempt++)
        {
            long attemptStart = System.currentTimeMillis();
            last = executeStepOnce(chain, step, attemptStart);
            last.setElapsedMs(System.currentTimeMillis() - stepStart);

            if (isRetryableEmptyResult(step, last))
            {
                last = OperationSyncResult.failed("chain:" + chain.code + ":" + step.code,
                        step.name, step.apiPath, "数据为空: total=0", last.getElapsedMs());
            }

            boolean ok = OperationSyncResult.STATUS_SUCCESS.equals(last.getStatus())
                    || OperationSyncResult.STATUS_SKIPPED.equals(last.getStatus());
            if (ok || attempt >= STEP_MAX_ATTEMPTS)
            {
                if (!ok && attempt > 1)
                {
                    last.setErrorMessage("重试" + attempt + "次后仍失败: " + last.getErrorMessage());
                }
                return last;
            }

            LOG.warn("链路 {} 步骤 {} 第{}次执行失败，{}秒后重试: {}",
                    chain.name, step.name, attempt, STEP_RETRY_DELAY_SECONDS, last.getErrorMessage());
            TimeUnit.SECONDS.sleep(STEP_RETRY_DELAY_SECONDS);
        }
        return last;
    }

    private OperationSyncResult executeStepOnce(Chain chain, StepDef step, long attemptStart)
    {
        Future<OperationSyncResult> future = executor.submit(() ->
                "amz_fba_box".equals(step.code) ? executeFbaBox(step) : step.runner.run());
        try
        {
            OperationSyncResult r = future.get(STEP_TIMEOUT_MINUTES, TimeUnit.MINUTES);
            r.setElapsedMs(System.currentTimeMillis() - attemptStart);
            return r;
        }
        catch (TimeoutException e)
        {
            future.cancel(true);
            LOG.error("步骤超时 [{}] {}: >{}min", chain.code, step.name, STEP_TIMEOUT_MINUTES);
            return OperationSyncResult.timeout("chain:" + chain.code + ":" + step.code,
                    step.name, step.apiPath, "超时(" + STEP_TIMEOUT_MINUTES + "min)",
                    System.currentTimeMillis() - attemptStart);
        }
        catch (Exception e)
        {
            LOG.error("步骤异常 [{}] {}: {}", chain.code, step.name, e.getMessage(), e);
            return OperationSyncResult.failed("chain:" + chain.code + ":" + step.code,
                    step.name, step.apiPath, rootMessage(e), System.currentTimeMillis() - attemptStart);
        }
    }

    private boolean isRetryableEmptyResult(StepDef step, OperationSyncResult r)
    {
        return !step.zeroAllowed
                && OperationSyncResult.STATUS_SUCCESS.equals(r.getStatus())
                && r.getTotalCount() == 0
                && r.getSuccessCount() == 0;
    }

    private String rootMessage(Exception e)
    {
        Throwable t = e;
        while (t.getCause() != null) t = t.getCause();
        return t.getMessage() != null ? t.getMessage() : e.getMessage();
    }

    private OperationSyncResult executeFbaBox(StepDef step) throws Exception
    {
        int closed = countClosedShipments(5);
        if (closed == 0)
            return OperationSyncResult.skipped("chain:fba:amz_fba_box", step.name, step.apiPath,
                    "最近5天无已完成货件", 0);
        OperationSyncResult r = step.runner.run();
        if (r.getTotalCount() == 0 && r.getSuccessCount() == 0)
            return OperationSyncResult.failed("chain:fba:amz_fba_box", step.name, step.apiPath,
                    "有" + closed + "条已完成货件但装箱0条", r.getElapsedMs());
        return r;
    }

    private int countClosedShipments(int days)
    {
        try {
            List<Map<String, Object>> list = SpringUtils.getBean(AmzFbaShipmentMapper.class).selectClosedSidShipmentByDays(days);
            return list != null ? list.size() : 0;
        } catch (Exception e) { LOG.warn("查询已完成货件数失败: {}", e.getMessage()); return -1; }
    }

    // ==================== 告警委托 ====================

    private String buildStepFailureDetail(Chain chain, StepDef step, OperationSyncResult r, Long childId)
    {
        StringBuilder sb = new StringBuilder();
        sb.append("链路=").append(chain.name)
                .append("(").append(chain.code).append(")")
                .append("；步骤=").append(step.name)
                .append("(").append(step.code).append(")")
                .append("；接口=").append(step.apiPath)
                .append("；状态=").append(r.getStatus());
        if (r.getErrorMessage() != null && !r.getErrorMessage().isEmpty())
        {
            sb.append("；原因=").append(r.getErrorMessage());
        }
        if (childId != null)
        {
            sb.append("；子日志ID=").append(childId);
        }
        return sb.toString();
    }

    private void trySendAlert(String chainCode, String stepCode, String stepName, String apiPath,
                              String status, String error, Long logId)
    {
        try {
            SyncAlertService svc = SpringUtils.getBean(SyncAlertService.class);
            if (svc != null) svc.sendAlert(chainCode, stepCode, stepName, apiPath, status, error, logId);
        }
        catch (Exception e) { LOG.warn("触发企微告警失败 [{}:{}]: {}", chainCode, stepCode, e.getMessage(), e); }
    }

    private void trySendRecovery(String chainCode, String stepCode, String stepName, Long logId)
    {
        try {
            SyncAlertService svc = SpringUtils.getBean(SyncAlertService.class);
            if (svc != null) svc.checkAndSendRecovery(chainCode, stepCode, stepName, logId);
        }
        catch (Exception e) { LOG.warn("触发企微恢复通知失败 [{}:{}]: {}", chainCode, stepCode, e.getMessage(), e); }
    }
}
