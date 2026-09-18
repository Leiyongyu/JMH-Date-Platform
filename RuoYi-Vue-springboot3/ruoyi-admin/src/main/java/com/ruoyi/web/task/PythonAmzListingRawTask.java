package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Isolated Python raw source; never writes the legacy AMZ replenishment listing table. */
@Component("pythonAmzListingRawTask")
public class PythonAmzListingRawTask
{
    private static final String CODE = "lingxing_amz_listing_raw_sync";
    private static final String NAME = "领星-AMZ刊登原始数据每周同步";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonAmzListingRawTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    public void runWeekly()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-amz-listing-raw-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runAmzListingRaw(requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int source = ((Number) details.get("extract_rows")).intValue();
            int stored = ((Number) details.get("ods_rows")).intValue();
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH,
                    source, stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("独立原始表全量覆盖；店铺数=" + details.get("shop_count")
                    + "；写入=" + stored + "；batch=" + details.get("sync_batch_id") + "；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult result = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new IllegalStateException("AMZ原始刊登同步失败，requestId=" + requestId, e);
        }
    }
}
