package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** eBay official seller listings; account-isolated source, monthly on day 5 at 05:00. */
@Component("pythonEbayStoreListingTask")
public class PythonEbayStoreListingTask
{
    private static final String CODE = "ebay_store_listing_sync";
    private static final String NAME = "eBay店铺商品信息每月同步";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonEbayStoreListingTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    public void runMonthly()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-ebay-store-listing-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runEbayStoreListing(requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int source = ((Number) details.get("extract_rows")).intValue();
            int stored = ((Number) details.get("ods_rows")).intValue();
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH,
                    source, stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("按账号完整校验后覆盖；店铺数=" + details.get("shop_count")
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
            throw new IllegalStateException("eBay店铺商品同步失败，requestId=" + requestId, e);
        }
    }
}
