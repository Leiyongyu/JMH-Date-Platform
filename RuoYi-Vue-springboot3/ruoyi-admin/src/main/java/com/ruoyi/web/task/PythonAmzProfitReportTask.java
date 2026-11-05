package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 每月7日05:00拉取上月领星利润统计（结算）与订单利润，供AMZ利润报表及其他报表复用。 */
@Component("pythonAmzProfitReportTask")
public class PythonAmzProfitReportTask
{
    private static final String CODE = "amz_profit_report_sync";
    private static final String NAME = "AMZ利润报表数据拉取";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private static final int MAX_RANGE_MONTHS = 12;
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonAmzProfitReportTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    /** 默认拉取上一个完整自然月。 */
    public void syncPreviousMonth()
    {
        execute(null);
    }

    /** 供任务页面按月补跑，例如 syncMonth('2026-09')。 */
    public void syncMonth(String statMonth)
    {
        execute(statMonth);
    }

    /**
     * 按月份范围依次补拉，例如 syncMonthRange('2026-07', '2026-09')。
     * 每个月单独拉取、单独记日志；某月失败不影响后续月份，全部跑完后汇总报错。
     */
    public void syncMonthRange(String startMonth, String endMonth)
    {
        YearMonth start = YearMonth.parse(startMonth.trim());
        YearMonth end = YearMonth.parse(endMonth.trim());
        if (start.isAfter(end))
        {
            throw new IllegalArgumentException("AMZ利润报表补拉：开始月份不能晚于结束月份");
        }
        if (start.plusMonths(MAX_RANGE_MONTHS).isBefore(end.plusMonths(1)))
        {
            throw new IllegalArgumentException("AMZ利润报表补拉：一次最多补拉" + MAX_RANGE_MONTHS + "个月");
        }
        List<String> failed = new ArrayList<>();
        for (YearMonth month = start; !month.isAfter(end); month = month.plusMonths(1))
        {
            try
            {
                execute(month.toString());
            }
            catch (RuntimeException e)
            {
                failed.add(month + "：" + e.getMessage());
            }
        }
        if (!failed.isEmpty())
        {
            throw new IllegalStateException("AMZ利润报表补拉有月份失败（其余月份已完成）："
                    + String.join("；", failed));
        }
    }

    private void execute(String statMonth)
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-amz-profit-report-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runAmzProfitReport(statMonth, requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int source = ((Number) details.get("extract_rows")).intValue();
            int stored = ((Number) details.get("ods_rows")).intValue();
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH,
                    source, stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("月份" + details.get("stat_month")
                    + "；结算店铺日记录=" + details.get("seller_rows")
                    + "；结算MSKU=" + details.get("msku_rows")
                    + "；订单利润MSKU=" + details.get("order_rows")
                    + "；batch=" + details.get("sync_batch_id") + "；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult result = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new IllegalStateException("AMZ利润报表数据拉取失败，requestId=" + requestId, e);
        }
    }
}
