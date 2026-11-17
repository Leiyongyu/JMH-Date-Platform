package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 飞书「汽配订单」未完成采购单同步：每天 08:00 / 13:00 / 18:00，供 eBay 补货2.0 的物流状态（采购单状态、下单日期、预计发货时间）使用。
 * 需要立即看到飞书里的改动时，在定时任务页面对本任务「执行一次」。
 */
@Component("pythonFeishuAutoPartsOrderTask")
public class PythonFeishuAutoPartsOrderTask
{
    private static final String CODE = "feishu_auto_parts_order_sync";
    private static final String NAME = "飞书汽配订单同步";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/" + CODE + "/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonFeishuAutoPartsOrderTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    public void run()
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-feishu-auto-parts-order-" + UUID.randomUUID();
        Long logId = logs.start(CODE, NAME, PATH, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runFeishuAutoPartsOrder(requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int fetched = ((Number) details.get("fetched_rows")).intValue();
            int stored = ((Number) details.get("inserted_rows")).intValue();
            OperationSyncResult result = OperationSyncResult.success(CODE, NAME, PATH,
                    fetched, stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary("只同步未完成采购单，整表替换；飞书行数=" + fetched
                    + "；eBay仓=" + details.get("ebay_rows")
                    + "；认出站点=" + details.get("ebay_open_rows")
                    + "；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult result = OperationSyncResult.failed(CODE, NAME, PATH,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new IllegalStateException("飞书汽配订单同步失败，requestId=" + requestId, e);
        }
    }
}
