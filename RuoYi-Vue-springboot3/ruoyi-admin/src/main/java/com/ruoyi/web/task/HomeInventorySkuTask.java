package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PerformancePythonClient;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 月末记录当时真实在售SKU数；不拉取外部接口，不接受补填历史月份。 */
@Component("homeInventorySkuTask")
public class HomeInventorySkuTask
{
    private final PerformancePythonClient client;
    public HomeInventorySkuTask(PerformancePythonClient client) { this.client = client; }
    public void captureMonthly()
    {
        OperationSyncContext.clear();
        long started = System.currentTimeMillis();
        Map<?, ?> report = (Map<?, ?>) client.captureHomeProductNature("inventory-sku-" + UUID.randomUUID()).get("data");
        if (report == null || report.get("stat_month") == null || !(report.get("total") instanceof Number))
            throw new IllegalStateException("库存看板SKU快照返回不完整");
        var result = OperationSyncResult.success("home_inventory_sku", "首页在售SKU月度快照",
                "homeInventorySkuTask.captureMonthly()", 1, 1, System.currentTimeMillis() - started);
        result.setBusinessSummary("统计月份=" + report.get("stat_month") + "；SKU=" + report.get("total")
                + "；实际采集=" + report.get("captured_at"));
        OperationSyncContext.set(result);
    }
}
