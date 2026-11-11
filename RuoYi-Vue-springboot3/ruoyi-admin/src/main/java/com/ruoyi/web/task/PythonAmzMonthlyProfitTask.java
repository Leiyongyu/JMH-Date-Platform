package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 每月7日06:00拉取上个完整自然月的领星利润报表（MSKU + 店铺，结算口径，人民币），供「AMZ月度利润表」使用。
 * 领星月结后数据仍会调整（尤其FBA途损），每次拉取整月替换，报表即拉取时的快照；需要按最新数重出时对本任务执行 syncMonth。
 */
@Component("pythonAmzMonthlyProfitTask")
public class PythonAmzMonthlyProfitTask
{
    private static final String CODE = "amz_monthly_profit_sync";
    private static final String NAME = "AMZ月度利润表数据拉取";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonAmzMonthlyProfitTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    /** 默认拉取上一个完整自然月。 */
    public void syncPreviousMonth()
    {
        execute(null);
    }

    /** 供任务页面按月补拉 / 重出，例如 syncMonth('2026-09')。 */
    public void syncMonth(String statMonth)
    {
        execute(statMonth == null ? null : statMonth.trim());
    }

    private void execute(String statMonth)
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-amz-monthly-profit-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runAmzMonthlyProfit(statMonth, requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int source = ((Number) details.get("extract_rows")).intValue();
            int stored = ((Number) details.get("ods_rows")).intValue();
            Object diffs = details.get("reconcile_diff_stores");
            int diffCount = diffs instanceof List<?> list ? list.size() : 0;
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH,
                    source, stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("月份" + details.get("stat_month")
                    + "；MSKU=" + details.get("msku_rows") + "；店铺=" + details.get("seller_rows")
                    + "；MSKU与店铺报表不一致的店铺=" + diffCount
                    + "；FBA途损合计=" + details.get("transit_loss_total")
                    + "；拉取时间=" + details.get("pulled_at")
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
            throw new IllegalStateException("AMZ月度利润表数据拉取失败，requestId=" + requestId, e);
        }
    }
}
