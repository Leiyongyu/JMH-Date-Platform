package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Current purchase transit; daily at 08:30 Asia/Shanghai. */
@Component("pythonInventoryPurchaseOrderTask")
public class PythonInventoryPurchaseOrderTask
{
    private static final String CODE = "monthly_inventory_purchase_order_sync";
    private static final String NAME = "月度库存采购在途同步";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonInventoryPurchaseOrderTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    { this.client = client; this.logs = logs; }

    public void sync()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-purchase-order-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<?, ?> data = (Map<?, ?>) client.runInventoryPurchaseOrders(requestId).get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            var result = OperationSyncResult.success(CODE, NAME, PATH,
                    ((Number) details.get("extract_rows")).intValue(),
                    ((Number) details.get("ods_rows")).intValue(), System.currentTimeMillis() - started);
            result.setDetails(Map.of("result", details));
            result.setBusinessSummary("报表月份=" + details.get("report_month")
                    + "；待到货=" + details.get("total_pending_arrival_qty")
                    + "；未税成本=" + details.get("total_pending_cost"));
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            var failed = OperationSyncResult.failed(CODE, NAME, PATH,
                    "采购在途同步失败；requestId=" + requestId + "；请查看Python任务记录",
                    System.currentTimeMillis() - started);
            logs.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException("采购在途同步失败；requestId=" + requestId);
        }
    }
}
