package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * eBay「周五数据」（运营中心 / eBay / 数据报表）：每周五 06:00 依次执行
 * 拉 eBay 在售刊登 → 拉谷仓区域仓库存 → 生成「有货无货」「海外仓库存」两张表的当周快照。
 * <ul>
 *   <li>listing 失败：整个任务失败，不生成报表（避免用上周的链接冒充本周）。</li>
 *   <li>谷仓失败：单独告警，仍用上一份谷仓快照生成，摘要与页面都写明谷仓数据的拉取时间。</li>
 * </ul>
 * 需要立即重算时在定时任务页面对本任务「执行一次」，或在页面上用现有快照重新生成。
 */
@Component("pythonEbayFridayReportTask")
public class PythonEbayFridayReportTask
{
    private static final String CODE = "ebay_friday_report_weekly";
    private static final String NAME = "eBay周五数据每周生成";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/ebay_friday_report_generate/run";
    private static final String ALERT_CHAIN = "ebay";
    private static final Logger LOG = LoggerFactory.getLogger(PythonEbayFridayReportTask.class);

    private final PythonPerformanceSchedulerClient scheduler;
    private final IOperationSyncLogService logs;
    private final SyncAlertService alerts;

    public PythonEbayFridayReportTask(PythonPerformanceSchedulerClient scheduler, IOperationSyncLogService logs,
            SyncAlertService alerts)
    {
        this.scheduler = scheduler;
        this.logs = logs;
        this.alerts = alerts;
    }

    public void runWeekly()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-ebay-friday-report-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<?, ?> listing = result(scheduler.runEbayStoreListing(requestId + "-listing"), "eBay在售刊登同步");
            int listingRows = intValue(listing.get("ods_rows"));
            if (listingRows <= 0)
                throw new IllegalStateException("eBay在售刊登同步返回空快照：写入=" + listingRows + "，不生成周五数据");
            String goodcangNote = runGoodcang(requestId);
            Map<?, ?> report = result(scheduler.runEbayFridayReport(requestId + "-report"), "周五数据生成");
            OperationSyncResult success = OperationSyncResult.success(CODE, NAME, PATH,
                    intValue(report.get("extract_rows")), intValue(report.get("ods_rows")),
                    System.currentTimeMillis() - started);
            success.setBusinessSummary("报表日期=" + report.get("report_date")
                    + "；listing=" + report.get("listing_count")
                    + "（站点不符=" + report.get("site_mismatch") + "，在线有货海外无货=" + report.get("online_without_stock") + "）"
                    + "；海外仓库存=" + report.get("stock_rows") + "行（无链接=" + report.get("stock_no_link") + "）"
                    + "；eBay刊登写入=" + listingRows + "；" + goodcangNote + "；requestId=" + requestId);
            logs.finish(logId, success);
            OperationSyncContext.set(success);
            alerts.checkAndSendRecovery(ALERT_CHAIN, CODE, NAME, logId);
        }
        catch (Exception e)
        {
            OperationSyncResult failed = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException("eBay周五数据生成失败，requestId=" + requestId, e);
        }
    }

    /** 谷仓失败不阻止生成：用上一份谷仓快照，页面显示谷仓拉取时间。 */
    private String runGoodcang(String requestId)
    {
        String goodcangRequestId = requestId + "-goodcang";
        try
        {
            Map<?, ?> details = result(scheduler.runGoodcangProductInventory(goodcangRequestId), "谷仓库存同步");
            int stored = intValue(details.get("ods_rows"));
            if (stored <= 0) throw new IllegalStateException("谷仓库存同步返回空快照：写入=" + stored);
            alerts.checkAndSendRecovery(ALERT_CHAIN, CODE + ":goodcang", NAME + "（谷仓库存）", null);
            return "谷仓库存同步成功：写入=" + stored;
        }
        catch (RuntimeException e)
        {
            LOG.warn("周五数据：谷仓库存同步失败，改用上一份谷仓快照生成 requestId={}: {}", goodcangRequestId, e.getMessage());
            alerts.sendAlert(ALERT_CHAIN, CODE + ":goodcang", NAME + "（谷仓库存）",
                    "/api/v1/internal/scheduler/tasks/goodcang_product_inventory_sync/run", "FAILED",
                    "谷仓库存同步失败，周五数据改用上一份谷仓快照生成：" + e.getMessage(), null);
            return "本次谷仓未更新（已告警，用上一份谷仓快照）：" + e.getMessage();
        }
    }

    private static Map<?, ?> result(Map<String, Object> response, String step)
    {
        if (response == null || !(response.get("data") instanceof Map<?, ?> data)
                || !(data.get("result") instanceof Map<?, ?> details))
            throw new IllegalStateException("Python未返回" + step + "结果，请确认已部署并重启最新Python服务");
        return details;
    }

    private static int intValue(Object value)
    {
        if (value instanceof Number number) return number.intValue();
        try { return Integer.parseInt(String.valueOf(value).trim()); }
        catch (RuntimeException ignored) { return -1; }
    }
}
