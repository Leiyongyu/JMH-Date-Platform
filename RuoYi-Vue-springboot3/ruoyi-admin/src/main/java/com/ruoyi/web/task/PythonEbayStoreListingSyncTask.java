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
 * eBay 在售刊登日级同步：价格分析看板的上游。
 *
 * <p>实测规模 37 个账号 / 18013 条 listing，一轮约 240 次 eBay Trading API 调用，
 * 占默认 5000 calls/day 额度的 5%，日级安全。
 *
 * <p>只调用 Python 既有的 {@code ebay_store_listing_sync}（即
 * {@code sync_ebay_store_listings}）复用全量逻辑，不改那边任何代码；
 * 拉取成功后直接执行一次价格分析刷表（锁冲突时重试一次，仍失败只告警，不推翻 listing）。
 *
 * <p>失败告警走两条路：Quartz 全局邮件通知（任务抛异常即触发），
 * 以及这里的快照新鲜度巡检 —— 2026-09-23 之后这份数据停了 7 周没人发现，
 * 就是因为任务不跑时根本没有失败可告警。
 */
@Component("pythonEbayStoreListingSyncTask")
public class PythonEbayStoreListingSyncTask
{
    private static final String CODE = "ebay_price_analysis_daily_sync";
    private static final String NAME = "eBay在售刊登与价格分析每日同步";
    private static final String PATH =
            "/api/v1/internal/scheduler/tasks/ebay_store_listing_sync/run";
    private static final String ALERT_CHAIN = "ebay";
    private static final String STALE_CODE = "ebay_price_analysis_snapshot_stale";
    private static final String STALE_NAME = "eBay价格分析快照新鲜度巡检";
    private static final Logger LOG =
            LoggerFactory.getLogger(PythonEbayStoreListingSyncTask.class);

    private final PythonPerformanceSchedulerClient scheduler;
    private final EbayPriceAnalysisPythonClient priceAnalysis;
    private final IOperationSyncLogService logs;
    private final SyncAlertService alerts;

    /** 快照超过这个天数就告警；日级同步正常时快照最多落后 1 天。 */
    @Value("${ebay.price-analysis.stale-alert.max-age-days:2}")
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

    /** Quartz 每日调用目标：拉 listing，成功后执行价格分析刷表。 */
    public void runDaily()
    {
        execute(true);
    }

    /** 只拉 listing 不刷表，排查上游问题时用。 */
    public void syncListingOnly()
    {
        execute(false);
    }

    private void execute(boolean refreshPriceAnalysis)
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

            String refreshNote = refreshPriceAnalysis
                    ? runRefresh(requestId)
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
                    "eBay在售刊登每日同步失败，requestId=" + requestId, e);
        }
    }

    /**
     * listing 同步成功后直接执行一次刷表（走调度通道，异步提交后轮询，总等待上限是 ETL 超时）。
     * 刷表与 listing 同步、在售售价同步共用锁 ebay:store-listing:replace；刚释放锁就被在售售价同步
     * 抢走时 Python 返回 409，这种情况等一会儿重试一次。仍失败则不推翻已经拉好的 listing：
     * 记在摘要里并单独告警，看板读到的是上一次快照。
     * 页面不再提供触发刷表的入口：重算 DWS 只走定时任务 ebay_price_analysis_refresh，
     * 重拉 eBay 并重算走本任务 runDaily()。
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
     * 只在成功读到 stat_date 时才发邮件；接口尚未部署或暂时不可用只记日志，不误报。
     */
    @Scheduled(cron = "0 20 9 * * *", zone = "Asia/Shanghai")
    public void checkSnapshotFreshness()
    {
        if (!staleAlertEnabled) return;
        LocalDate snapshot;
        try
        {
            Map<String, Object> response = priceAnalysis.overview(
                    Map.of(), "ebay-price-analysis-freshness-" + UUID.randomUUID());
            if (!(response.get("data") instanceof Map<?, ?> data))
            {
                LOG.warn("eBay价格分析快照巡检跳过：响应没有 data 节点");
                return;
            }
            snapshot = parseDate(data.get("stat_date"));
            if (snapshot == null)
            {
                LOG.warn("eBay价格分析快照巡检跳过：stat_date 缺失或不可解析={}",
                        data.get("stat_date"));
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
