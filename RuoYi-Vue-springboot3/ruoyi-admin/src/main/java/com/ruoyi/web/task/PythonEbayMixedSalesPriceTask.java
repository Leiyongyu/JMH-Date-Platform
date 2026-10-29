package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Monthly native-currency listing prices; day 3, 07:00 Asia/Shanghai. */
@Component("pythonEbayMixedSalesPriceTask")
public class PythonEbayMixedSalesPriceTask
{
    private static final String CODE="ebay_mixed_sales_price_sync";
    private static final String NAME="混销-eBay在售售价月度同步";
    private static final String PATH="/api/v1/internal/scheduler/tasks/"+CODE+"/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;
    public PythonEbayMixedSalesPriceTask(PythonPerformanceSchedulerClient client,IOperationSyncLogService logs)
    { this.client=client;this.logs=logs; }

    public void runMonthly()
    {
        long began=System.currentTimeMillis();
        String requestId="quartz-ebay-mixed-price-"+UUID.randomUUID();
        Long logId=logs.start(CODE,NAME,PATH,"JOB","SYSTEM",null,null);
        try
        {
            Map<?,?> data=(Map<?,?>)client.runEbayMixedSalesPrices(requestId).get("data");
            Map<?,?> details=(Map<?,?>)data.get("result");
            int rows=((Number)details.get("extract_rows")).intValue();
            var result=OperationSyncResult.success(CODE,NAME,PATH,rows,rows,System.currentTimeMillis()-began);
            result.setDetails(Map.of("result",details));
            result.setBusinessSummary("月份="+details.get("stat_month")+"；店铺数="+details.get("shop_count")+"；在售刊登="+rows+"；缺授权跳过="+details.get("skipped_rows"));
            logs.finish(logId,result); OperationSyncContext.set(result);
        }
        catch(Exception exc)
        {
            var failed=OperationSyncResult.failed(CODE,NAME,PATH,"同步失败；requestId="+requestId+"；请查看Python任务记录",System.currentTimeMillis()-began);
            logs.finish(logId,failed);OperationSyncContext.set(failed);
            throw new IllegalStateException("混销售价同步失败；requestId="+requestId);
        }
    }
}
