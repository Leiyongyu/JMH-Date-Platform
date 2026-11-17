package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 「eBay月度利润表」的两个月度拉取，与 AMZ月度利润表（每月7日06:00）同一天、在它之前跑：
 * <ul>
 *   <li>05:00 谷仓账单：上个月 eBay 账户（ACG1064502）的账单费用明细（尾程、仓储等）；</li>
 *   <li>05:30 eBay 交易流水：上个月全部店铺的 Finances 交易（太平洋时间切月，与卖家后台交易报告一致）。</li>
 * </ul>
 * 两者都整月替换，报表在页面打开时按最新数据现算；需要重出某个月时对本任务执行 xxxMonth('2026-10')。
 */
@Component("pythonEbayMonthlyProfitTask")
public class PythonEbayMonthlyProfitTask
{
    static final String BILL_CODE = "goodcang_bill_monthly_sync";
    static final String BILL_NAME = "eBay月度利润表-谷仓账单拉取";
    static final String FINANCE_CODE = "ebay_finance_monthly_sync";
    static final String FINANCE_NAME = "eBay月度利润表-交易流水拉取";
    private static final String PATH = "/api/v1/internal/scheduler/tasks/%s/run";
    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logs;

    public PythonEbayMonthlyProfitTask(PythonPerformanceSchedulerClient client, IOperationSyncLogService logs)
    {
        this.client = client;
        this.logs = logs;
    }

    /** 每月7日05:00：上个月谷仓账单。 */
    public void syncGoodcangBillPreviousMonth()
    {
        execute(BILL_CODE, BILL_NAME, null);
    }

    /** 每月7日05:30：上个月 eBay 交易流水。 */
    public void syncEbayFinancePreviousMonth()
    {
        execute(FINANCE_CODE, FINANCE_NAME, null);
    }

    /** 按月补拉谷仓账单，例如 syncGoodcangBillMonth('2026-10')。 */
    public void syncGoodcangBillMonth(String statMonth)
    {
        execute(BILL_CODE, BILL_NAME, statMonth == null ? null : statMonth.trim());
    }

    /** 按月补拉 eBay 交易流水，例如 syncEbayFinanceMonth('2026-10')。 */
    public void syncEbayFinanceMonth(String statMonth)
    {
        execute(FINANCE_CODE, FINANCE_NAME, statMonth == null ? null : statMonth.trim());
    }

    private void execute(String code, String name, String statMonth)
    {
        long started = System.currentTimeMillis();
        String path = String.format(PATH, code);
        String requestId = "quartz-" + code.replace('_', '-') + "-" + UUID.randomUUID();
        Long logId = logs.start(code, name, path, "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = BILL_CODE.equals(code)
                    ? client.runGoodcangBill(statMonth, requestId)
                    : client.runEbayFinance(statMonth, requestId);
            Map<?, ?> data = (Map<?, ?>) response.get("data");
            Map<?, ?> details = (Map<?, ?>) data.get("result");
            int source = number(details.get("extract_rows"));
            int stored = number(details.get("ods_rows"));
            OperationSyncResult result = OperationSyncResult.success(code, name, path,
                    source, stored, System.currentTimeMillis() - started);
            result.setDetails(response);
            result.setBusinessSummary(summary(code, details) + "；batch=" + details.get("sync_batch_id")
                    + "；requestId=" + requestId);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult result = OperationSyncResult.failed(code, name, path,
                    "requestId=" + requestId + "；" + e.getMessage(), System.currentTimeMillis() - started);
            logs.finish(logId, result);
            OperationSyncContext.set(result);
            throw new IllegalStateException(name + "失败，requestId=" + requestId, e);
        }
    }

    static String summary(String code, Map<?, ?> details)
    {
        if (BILL_CODE.equals(code))
            return "月份" + details.get("stat_month") + "；账单=" + details.get("bills")
                    + "；费用行=" + details.get("ods_rows") + "；拉取时间=" + details.get("pulled_at");
        Object failed = details.get("failed_stores");
        int failedCount = failed instanceof Map<?, ?> map ? map.size() : 0;
        return "月份" + details.get("stat_month") + "；店铺=" + details.get("store_count")
                + "；失败店铺=" + failedCount + "；交易行=" + details.get("ods_rows")
                + "；缺SKU的订单行=" + details.get("missing_sku_rows") + "；拉取时间=" + details.get("pulled_at");
    }

    private static int number(Object value)
    {
        return value instanceof Number n ? n.intValue() : 0;
    }
}
