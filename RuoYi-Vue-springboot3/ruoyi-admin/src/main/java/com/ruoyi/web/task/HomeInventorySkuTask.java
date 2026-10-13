package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PerformancePythonClient;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 保留旧 Quartz 调用目标；实际执行首页商品性质月末快照采集。 */
@Component("homeInventorySkuTask")
public class HomeInventorySkuTask
{
    private final PerformancePythonClient client;
    public HomeInventorySkuTask(PerformancePythonClient client) { this.client = client; }
    public void captureMonthly()
    {
        OperationSyncContext.clear();
        long started = System.currentTimeMillis();
        Map<?, ?> report = (Map<?, ?>) client.captureHomeProductNature("product-nature-" + UUID.randomUUID()).get("data");
        if (report == null || report.get("stat_month") == null || !(report.get("total") instanceof Number))
            throw new IllegalStateException("商品性质月末快照返回不完整");
        var result = OperationSyncResult.success("home_product_nature", "首页商品性质月末快照",
                "homeInventorySkuTask.captureMonthly()", 1, 1, System.currentTimeMillis() - started);
        result.setBusinessSummary("统计月份=" + report.get("stat_month") + "；SKU=" + report.get("total")
                + "；实际采集=" + report.get("captured_at"));
        OperationSyncContext.set(result);
    }
}
