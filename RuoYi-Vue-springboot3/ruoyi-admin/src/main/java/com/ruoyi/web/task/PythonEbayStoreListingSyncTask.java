package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.ebay.EbayPriceAnalysisPythonClient;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * eBay 在售刊登与谷仓库存每周同步：价格分析看板的上游（每周一 04:30）。
 *
 * <p>依次执行三步：拉 eBay listing → 拉谷仓区域仓库存 → 刷价格分析 DWS。
 * <ul>
 *   <li>listing 失败：整个任务失败，不刷表。</li>
 *   <li>谷仓失败：不推翻已拉好的 listing，单独告警，仍继续刷表（用上一份谷仓快照），
 *       摘要写明「本次谷仓未更新」。</li>
 *   <li>刷表遇锁冲突(409)：等一会儿重试一次，仍失败只告警，不推翻 listing。</li>
 * </ul>
 *
 * <p>listing 调用 Python 既有的 {@code ebay_store_listing_sync}（实测 37 个账号 / 18013 条，
 * 一轮约 240 次 eBay Trading API 调用）；谷仓调用 {@code goodcang_product_inventory_sync}，
 * 它用单独的锁、整表单事务替换，不需要与刷表共锁。
 *
 * <p>{@code runDaily()} 只是过渡用的兼容入口（转调 {@code runWeekly()}），等部署机和本机的
 * {@code 20261110_ebay_price_analysis_weekly_goodcang.sql} 都执行过就删掉。
 *
 * <p>失败告警走两条路：Quartz 全局邮件通知（任务抛异常即触发），
 * 以及这里的快照新鲜度巡检 —— 2026-09-23 之后这份数据停了 7 周没人发现，
 * 就是因为任务不跑时根本没有失败可告警。
 */
@Component("pythonEbayStoreListingSyncTask")
public class PythonEbayStoreListingSyncTask
{
    private static final String CODE = "ebay_price_analysis_weekly_sync";
    private static final String NAME = "eBay在售刊登、谷仓库存与价格分析每周同步";
    private static final String PATH =
            "/api/v1/internal/scheduler/tasks/ebay_store_listing_sync/run";
    private static final String GOODCANG_PATH =
            "/api/v1/internal/scheduler/tasks/goodcang_product_inventory_sync/run";
    private static final String ALERT_CHAIN = "ebay";
    private static final String STALE_CODE = "ebay_price_analysis_snapshot_stale";
    private static final String STALE_NAME = "eBay价格分析快照新鲜度巡检";
    private static final Logger LOG =
            LoggerFactory.getLogger(PythonEbayStoreListingSyncTask.class);

    private final PythonPerformanceSchedulerClient scheduler;
    private final EbayPriceAnalysisPythonClient priceAnalysis;
    private final IOperationSyncLogService logs;
    private final SyncAlertService alerts;

    /** 快照超过这个天数就告警；每周同步正常时快照最多落后 7 天，留 1 天余量。 */
    @Value("${ebay.price-analysis.stale-alert.max-age-days:8}")
    private int maxSnapshotAgeDays;

    @Value("${ebay.price-analysis.stale-alert.enabled:true}")
    private boolean staleAlertEnabled;

    /** 刷表遇到锁冲突(409)时，等待多久重试一次。 */
    @Value("${ebay.price-analysis.refresh-retry-delay-ms:60000}")
    long refreshRetryDelayMillis = 60_000;

    public PythonEbayStoreListingSyncTask(
            PythonPerformanceSchedulerClient scheduler,
            EbayPriceAnalysisPythonClient priceAnalysis,
            IOperationSyncLogService logs,
            SyncAlertService alerts)
    {
        this.scheduler = scheduler;
        this.priceAnalysis = priceAnalysis;
        this.logs = logs;
        this.alerts = alerts;
    }

    /** Quartz 每周调用目标：拉 listing → 拉谷仓库存 → 执行价格分析刷表。 */
    public void runWeekly()
    {
        execute(true);
    }

    /**
     * 过渡用的旧任务入口：sys_job 仍指向 runDaily() 时转调 {@link #runWeekly()}，避免
     * 新版 Java 先上线、改频率的 SQL 晚执行时 04:30 那次因找不到方法而失败。
     * 等部署机和本机都执行过 20261110_ebay_price_analysis_weekly_goodcang.sql 后删掉本方法。
     */
    @Deprecated
    public void runDaily()
    {
        LOG.warn("旧任务入口 runDaily() 仍在被调用，说明 20261110_ebay_price_analysis_weekly_goodcang.sql"
                + " 尚未执行；本次按每周流程（listing → 谷仓 → 刷表）执行");
        runWeekly();
    }

    /** 只拉 listing，不拉谷仓也不刷表，排查上游问题时用。 */
    public void syncListingOnly()
    {
        execute(false);
    }

    private void execute(boolean fullWeeklyRun)
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-ebay-price-analysis-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = scheduler.runEbayStoreListing(requestId);
            Map<?, ?> details = result(response);
            int source = intValue(details.get("extract_rows"));
            int stored = intValue(details.get("ods_rows"));
            int shops = intValue(details.get("shop_count"));
            // 全量覆盖型同步返回空快照意味着上游异常，不能让看板读到被清空的表。
            if (stored <= 0 || shops <= 0)
                throw new IllegalStateException("eBay在售刊登同步返回空快照：写入=" + stored
                        + "，店铺数=" + shops + "；已按失败处理，不接受空的整表覆盖");

            // 谷仓失败不推翻 listing，也不阻止刷表（刷表用上一份谷仓快照）。
            String refreshNote = fullWeeklyRun
                    ? runGoodcang(requestId) + "；" + runRefresh(requestId)
                    : "本次只拉取 listing，未执行价格分析刷表";

            OperationSyncResult success = OperationSyncResult.success(CODE, NAME, PATH,
                    source, stored, System.currentTimeMillis() - started);
            success.setDetails(response);
            success.setBusinessSummary("按账号完整校验后覆盖；店铺数=" + shops
                    + "；写入=" + stored + "；batch=" + details.get("sync_batch_id")
                    + "；" + refreshNote + "；requestId=" + requestId);
            logs.finish(logId, success);
            OperationSyncContext.set(success);
            alerts.checkAndSendRecovery(ALERT_CHAIN, CODE, NAME, logId);
        }
        catch (Exception e)
        {
            OperationSyncResult failed = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(),
                    System.currentTimeMillis() - started);
            logs.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException(
                    "eBay在售刊登每周同步失败，requestId=" + requestId, e);
        }
    }

    /**
     * listing 同步成功后拉一次谷仓区域仓库存。谷仓同步单独一把锁、整表单事务替换，
     * 失败时只告警（告警码与刷表失败区分开），返回说明文字，调用方继续刷表。
     */
    private String runGoodcang(String requestId)
    {
        String goodcangRequestId = requestId + "-goodcang";
        try
        {
            Map<String, Object> response = scheduler.runGoodcangProductInventory(goodcangRequestId);
            if (response == null || !(response.get("data") instanceof Map<?, ?> data)
                    || !(data.get("result") instanceof Map<?, ?> details))
                throw new IllegalStateException("Python未返回谷仓库存同步结果，请确认已部署并重启最新Python服务");
            int stored = intValue(details.get("ods_rows"));
            // Python 端对空快照已判失败、不替换表；这里再兜一层，空结果不当成功。
            if (stored <= 0)
                throw new IllegalStateException("谷仓库存同步返回空快照：写入=" + stored);
            alerts.checkAndSendRecovery(ALERT_CHAIN, CODE + ":goodcang", NAME + "（谷仓库存）", null);
            return "谷仓库存同步成功：写入=" + stored + "，batch=" + details.get("sync_batch_id");
        }
        catch (RuntimeException e)
        {
            LOG.warn("谷仓库存同步失败，listing 已拉取成功，继续用上一份谷仓快照刷表 requestId={}: {}",
                    goodcangRequestId, e.getMessage());
            alerts.sendAlert(ALERT_CHAIN, CODE + ":goodcang", NAME + "（谷仓库存）", GOODCANG_PATH,
                    "FAILED", "listing 已拉取成功，但谷仓库存同步失败，本次谷仓未更新，"
                            + "价格分析继续用上一份谷仓快照刷表：" + e.getMessage(), null);
            return "本次谷仓未更新（谷仓库存同步失败，已告警）：" + e.getMessage();
        }
    }

    /**
     * listing 与谷仓同步之后执行一次刷表（走调度通道，异步提交后轮询，总等待上限是 ETL 超时）。
     * 刷表与 listing 同步、在售售价同步共用锁 ebay:store-listing:replace；刚释放锁就被在售售价同步
     * 抢走时 Python 返回 409，这种情况等一会儿重试一次。仍失败则不推翻已经拉好的 listing：
     * 记在摘要里并单独告警，看板读到的是上一次快照。
     * 页面不再提供触发刷表的入口：重算 DWS 只走定时任务 ebay_price_analysis_refresh，
     * 重拉 eBay、谷仓并重算走本任务 runWeekly()。
     */
    private String runRefresh(String requestId)
    {
        String refreshRequestId = requestId + "-refresh";
        boolean retried = false;
        try
        {
            Map<String, Object> response;
            try
            {
                response = scheduler.runEbayPriceAnalysisRefresh(refreshRequestId);
            }
            catch (RuntimeException first)
            {
                if (!isLockConflict(first)) throw first;
                retried = true;
                LOG.warn("eBay价格分析刷表遇到锁冲突(409)，{} 毫秒后重试一次 requestId={}: {}",
                        refreshRetryDelayMillis, refreshRequestId, first.getMessage());
                sleep(refreshRetryDelayMillis);
                response = scheduler.runEbayPriceAnalysisRefresh(refreshRequestId + "-retry");
            }
            if (response == null || !(response.get("data") instanceof Map<?, ?> data)
                    || !(data.get("result") instanceof Map<?, ?> details))
                throw new IllegalStateException("Python未返回价格分析刷表结果，请确认已部署并重启最新Python服务");
            return (retried ? "价格分析刷表首次遇锁冲突(409)，重试后成功" : "价格分析刷表成功")
                    + "：DWS行数=" + details.get("rows") + "，快照日期=" + details.get("stat_date")
                    + "，未匹配库存=" + unmatched(details);
        }
        catch (RuntimeException e)
        {
            String reason = (retried ? "首次遇锁冲突(409)，重试仍失败：" : "") + e.getMessage();
            LOG.warn("eBay价格分析刷表失败，listing 已拉取成功 requestId={}: {}",
                    refreshRequestId, reason);
            alerts.sendAlert(ALERT_CHAIN, CODE + ":refresh", NAME + "（刷表）",
                    "/api/v1/internal/scheduler/tasks/ebay_price_analysis_refresh/run", "FAILED",
                    "listing 已拉取成功，但价格分析刷表失败，看板仍是上一次快照：" + reason, null);
            return "价格分析刷表失败（已告警）：" + reason;
        }
    }

    /** 调度客户端把 Python 的 HTTP 状态写进异常信息：「...错误[HTTP 409]: ...」。 */
    static boolean isLockConflict(Throwable error)
    {
        for (Throwable current = error; current != null; current = current.getCause())
        {
            String message = current.getMessage();
            if (message != null && message.contains("[HTTP 409]")) return true;
        }
        return false;
    }

    private static Object unmatched(Map<?, ?> details)
    {
        Object rows = details.get("rows");
        Object matched = details.get("matched_rows");
        if (rows instanceof Number total && matched instanceof Number hit)
            return total.longValue() - hit.longValue();
        return "未知";
    }

    private static void sleep(long millis)
    {
        if (millis <= 0) return;
        try
        {
            Thread.sleep(millis);
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("等待重试价格分析刷表时被中断", e);
        }
    }

    /**
     * 每天 09:20 读看板快照日期，太旧就告警。
     * 快照日期取 /stores 响应顶层的 stat_date（看板已不再有 overview 接口）。
     * 接口调用本身失败（未部署、暂时不可用）只记日志，不误报；
     * 但接口有响应却读不到 stat_date（缺失、为空或不可解析）说明看板本身有问题，必须告警，
     * 不能静默跳过，否则巡检会悄悄失效。
     */
    @Scheduled(cron = "0 20 9 * * *", zone = "Asia/Shanghai")
    public void checkSnapshotFreshness()
    {
        if (!staleAlertEnabled) return;
        LocalDate snapshot;
        try
        {
            Map<String, Object> response = priceAnalysis.stores(
                    Map.of(), "ebay-price-analysis-freshness-" + UUID.randomUUID());
            Object rawDate = response != null && response.get("data") instanceof Map<?, ?> data
                    ? data.get("stat_date") : null;
            snapshot = parseDate(rawDate);
            if (snapshot == null)
            {
                alerts.sendAlert(ALERT_CHAIN, STALE_CODE, STALE_NAME, PATH, "STALE",
                        "eBay价格分析看板读不到快照日期（/stores 响应的 stat_date=" + rawDate
                                + "），看板可能为空或数据异常。请检查定时任务「" + NAME
                                + "」最近一次执行结果与价格分析刷表。",
                        null);
                return;
            }
        }
        catch (RuntimeException e)
        {
            LOG.warn("eBay价格分析快照巡检未能读到快照日期，本次不告警: {}", e.getMessage());
            return;
        }

        long ageDays = LocalDate.now().toEpochDay() - snapshot.toEpochDay();
        if (ageDays <= Math.max(maxSnapshotAgeDays, 1))
        {
            alerts.checkAndSendRecovery(ALERT_CHAIN, STALE_CODE, STALE_NAME, null);
            return;
        }
        alerts.sendAlert(ALERT_CHAIN, STALE_CODE, STALE_NAME, PATH, "STALE",
                "eBay价格分析看板快照日期=" + snapshot + "，已落后 " + ageDays
                        + " 天（阈值 " + Math.max(maxSnapshotAgeDays, 1)
                        + " 天）。请检查定时任务「" + NAME + "」是否被暂停，以及 eBay 账号授权是否过期。",
                null);
    }

    private static Map<?, ?> result(Map<String, Object> response)
    {
        if (!(response.get("data") instanceof Map<?, ?> data)
                || !(data.get("result") instanceof Map<?, ?> details))
            throw new IllegalStateException("Python未返回eBay在售刊登同步结果，请确认已部署并重启最新Python服务");
        return details;
    }

    private static int intValue(Object value)
    {
        if (value instanceof Number number) return number.intValue();
        try
        {
            return Integer.parseInt(String.valueOf(value).trim());
        }
        catch (RuntimeException ignored)
        {
            return -1;
        }
    }

    private static LocalDate parseDate(Object value)
    {
        if (value == null) return null;
        String text = String.valueOf(value).trim();
        if (text.length() < 10) return null;
        try
        {
            return LocalDate.parse(text.substring(0, 10));
        }
        catch (DateTimeParseException ignored)
        {
            return null;
        }
    }
}
