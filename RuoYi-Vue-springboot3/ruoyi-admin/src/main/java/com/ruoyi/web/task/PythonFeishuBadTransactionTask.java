package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Feishu bitable "bad transaction listings"; weekly on Wednesday 18:00, incremental by record_id. */
@Component("pythonFeishuBadTransactionTask")
public class PythonFeishuBadTransactionTask
{
    private static final String CODE = "feishu_bad_transaction_sync";
    private static final String NAME = "飞书不良交易刊登每周同步";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonFeishuBadTransactionTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    public void runWeekly()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-feishu-bad-transaction-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runFeishuBadTransaction(requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int source = ((Number) details.get("fetched_rows")).intValue();
            // 只有真正写进去的才算"入库"：内容没变的行不重写，不该计入。
            int stored = ((Number) details.get("inserted_rows")).intValue()
                    + ((Number) details.get("updated_rows")).intValue();
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH,
                    source, stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("按飞书record_id增量同步；拉取=" + source
                    + "；新增=" + details.get("inserted_rows")
                    + "；更新=" + details.get("updated_rows")
                    + "；未变=" + details.get("unchanged_rows")
                    + "；删除=" + details.get("deleted_rows")
                    + "；批次=" + details.get("batches") + "；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult result = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new IllegalStateException("飞书不良交易刊登同步失败，requestId=" + requestId, e);
        }
    }
}
