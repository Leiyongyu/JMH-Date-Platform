package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Separate from monthly inventory: all warehouses, live weekly snapshot only. */
@Component("pythonWeeklyInventoryTask")
public class PythonWeeklyInventoryTask
{
    private static final String CODE = "weekly_inventory_bin_export";
    private static final String NAME = "仓位库存明细周报";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonWeeklyInventoryTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    public void runWeekly()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-weekly-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runWeeklyInventory(requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> resultData = (Map<?, ?>) data.get("result");
            int source = ((Number) resultData.get("extract_rows")).intValue();
            int rows = ((Number) resultData.get("row_count")).intValue();
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH, source, source,
                    System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("已生成" + rows + "行；文件：" + resultData.get("file_name") + "；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult failed = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException("周报生成失败，requestId=" + requestId, e);
        }
    }
}
