package com.ruoyi.web.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Java Quartz 到Python月度库存源数据、清洗明细和部门汇总的调度桥接器。 */
@Component("pythonMonthlyInventoryReportTask")
public class PythonMonthlyInventoryReportTask
{
    private static final String SYNC_TYPE =
            "python_monthly_inventory_report_source";
    private static final String SYNC_NAME =
            "月度库存统计表数据拉取";
    private static final String API_PATH =
            "/api/v1/internal/scheduler/tasks/"
            + "monthly_inventory_report_source_sync/run";
    private static final String SALES_VOLUME_SYNC_TYPE =
            "python_monthly_inventory_report_sales_volume";
    private static final String SALES_VOLUME_SYNC_NAME =
            "月度库存实际达成及销量填充";
    private static final String SALES_VOLUME_API_PATH =
            "/api/v1/internal/scheduler/tasks/"
            + "monthly_inventory_report_sales_volume_sync/run";
    private static final String OPENING_INVENTORY_SYNC_TYPE =
            "python_monthly_inventory_report_opening_inventory";
    private static final String OPENING_INVENTORY_SYNC_NAME =
            "月度库存次月月初库存填充";
    private static final String OPENING_INVENTORY_API_PATH =
            "/api/v1/internal/scheduler/tasks/"
            + "monthly_inventory_report_opening_inventory_fill/run";
    private static final String CURRENCY_SYNC_TYPE =
            "python_lingxing_currency_month";
    private static final String CURRENCY_SYNC_NAME =
            "领星月度汇率同步";
    private static final String CURRENCY_API_PATH =
            "/api/v1/internal/scheduler/tasks/currency_month_sync/run";
    private static final DateTimeFormatter REQUEST_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logService;
    private final ObjectMapper objectMapper;

    public PythonMonthlyInventoryReportTask(
            PythonPerformanceSchedulerClient client,
            IOperationSyncLogService logService,
            ObjectMapper objectMapper)
    {
        this.client = client;
        this.logService = logService;
        this.objectMapper = objectMapper;
    }

    /** 每月先同步领星全部币种汇率，再拉取上一个完整自然月库存数据。 */
    public void syncPreviousMonth()
    {
        execute(null);
    }

    /** 兼容已经注册过的旧Quartz任务入口，实际口径同样为上一个完整自然月。 */
    public void syncCurrentMonth()
    {
        syncPreviousMonth();
    }

    /** 供任务页面按月补跑，例如 syncMonth('2026-08')。 */
    public void syncMonth(String statMonth)
    {
        execute(statMonth);
    }

    /** 每月1日12:00拉取上个完整自然月Amazon实际达成和销量。 */
    public void syncPreviousMonthSalesVolume()
    {
        execute(null, true);
    }

    /** 兼容旧Quartz调用入口，实际同样拉取上个完整自然月。 */
    public void syncCurrentMonthSalesVolume()
    {
        syncPreviousMonthSalesVolume();
    }

    /** 每月2日23:00使用上月期末数回填次月月初库存数量。 */
    public void fillPreviousMonthOpeningInventory()
    {
        execute(null, false, true);
    }

    /** 独立同步当前自然月的领星全部币种汇率；Quartz任务默认暂停。 */
    public void syncCurrentMonthCurrency()
    {
        executeCurrency(null);
    }

    /** 供任务页面按月补跑，例如 syncCurrencyMonth('2026-08')。 */
    public void syncCurrencyMonth(String statMonth)
    {
        executeCurrency(statMonth);
    }

    @SuppressWarnings("unchecked")
    private void execute(String statMonth)
    {
        execute(statMonth, false, false);
    }

    @SuppressWarnings("unchecked")
    private void execute(String statMonth, boolean salesVolumeOnly)
    {
        execute(statMonth, salesVolumeOnly, false);
    }

    @SuppressWarnings("unchecked")
    private void execute(
            String statMonth,
            boolean salesVolumeOnly,
            boolean openingInventoryOnly)
    {
        long started = System.currentTimeMillis();
        String requestId = requestId();
        String syncType = openingInventoryOnly
                ? OPENING_INVENTORY_SYNC_TYPE
                : salesVolumeOnly ? SALES_VOLUME_SYNC_TYPE : SYNC_TYPE;
        String syncName = openingInventoryOnly
                ? OPENING_INVENTORY_SYNC_NAME
                : salesVolumeOnly ? SALES_VOLUME_SYNC_NAME : SYNC_NAME;
        String apiPath = openingInventoryOnly
                ? OPENING_INVENTORY_API_PATH
                : salesVolumeOnly ? SALES_VOLUME_API_PATH : API_PATH;
        Long logId = logService.start(
                syncType, syncName, apiPath,
                "JOB", "SYSTEM", null, null);
        String requestParams = requestParams(statMonth, requestId);
        try
        {
            Map<String, Object> response =
                    openingInventoryOnly
                    ? client.runInventoryReportOpeningInventory(
                            statMonth, requestId)
                    : salesVolumeOnly
                    ? client.runInventoryReportSalesVolume(statMonth, requestId)
                    : client.runInventoryReportSources(statMonth, requestId);
            Map<String, Object> data = map(response.get("data"));
            Map<String, Object> resultData = map(data.get("result"));
            int fbaRows = integer(resultData.get("fba_rows"));
            int overseasRows = integer(resultData.get("overseas_rows"));
            int localRows = integer(resultData.get("local_rows"));
            int orderProfitRows = integer(
                    resultData.get("order_profit_rows"));
            int dwdRows = integer(resultData.get("dwd_rows"));
            int summaryRows = integer(resultData.get("summary_rows"));
            int total = integer(resultData.get("extract_rows"));

            OperationSyncResult result = OperationSyncResult.success(
                    syncType, syncName, apiPath,
                    total, integer(resultData.get("ods_rows")),
                    System.currentTimeMillis() - started);
            result.setRequestParams(requestParams);
            result.setDetails(response);
            if (openingInventoryOnly)
                result.setBusinessSummary(
                        "库存月份" + resultData.get("stat_month")
                        + "；月初库存月份"
                        + resultData.get("opening_month")
                        + "；回填部门汇总 "
                        + integer(resultData.get("updated_rows"))
                        + "条；requestId=" + requestId);
            else if (salesVolumeOnly)
                result.setBusinessSummary(
                        "业务月份" + resultData.get("stat_month")
                        + "；Amazon实际达成及销量 " + orderProfitRows + "条"
                        + "；按月覆盖ODS " + integer(resultData.get("ods_rows"))
                        + "条；销量DWD " + dwdRows
                        + "条；requestId=" + requestId);
            else
                result.setBusinessSummary(
                        "月份" + resultData.get("stat_month")
                        + "；FBA " + fbaRows + "条"
                        + "；海外仓 " + overseasRows + "条"
                        + "；本地仓 " + localRows + "条"
                        + "；DWD明细 " + dwdRows + "条"
                        + "；DWS汇总 " + summaryRows + "条"
                        + "；requestId=" + requestId);
            logService.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult failed = OperationSyncResult.failed(
                    syncType, syncName, apiPath,
                    "requestId=" + requestId + "；" + e.getMessage(),
                    System.currentTimeMillis() - started);
            failed.setRequestParams(requestParams);
            Map<String, Object> details = new LinkedHashMap<>();
            details.put("request_id", requestId);
            details.put("stat_month", statMonth);
            details.put("error", e.getMessage());
            failed.setDetails(details);
            logService.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException(
                    (openingInventoryOnly
                            ? "Python月度库存次月月初库存填充失败，requestId="
                            : salesVolumeOnly
                            ? "Python月度库存实际达成及销量填充失败，requestId="
                            : "Python月度库存报表源数据同步失败，requestId=")
                    + requestId + "：" + e.getMessage(), e);
        }
    }

    private String requestParams(String statMonth, String requestId)
    {
        try
        {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("pull_month", statMonth);
            params.put("trigger_type", "JOB");
            params.put("request_id", requestId);
            return objectMapper.writeValueAsString(params);
        }
        catch (Exception ignored)
        {
            return "{\"request_id\":\"" + requestId + "\"}";
        }
    }

    @SuppressWarnings("unchecked")
    private void executeCurrency(String statMonth)
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-currency-month-"
                + LocalDateTime.now().format(REQUEST_TIME)
                + "-"
                + UUID.randomUUID().toString().replace("-", "");
        Long logId = logService.start(
                CURRENCY_SYNC_TYPE, CURRENCY_SYNC_NAME, CURRENCY_API_PATH,
                "JOB", "SYSTEM", null, null);
        String requestParams = currencyRequestParams(statMonth, requestId);
        try
        {
            Map<String, Object> response =
                    client.runCurrencyMonth(statMonth, requestId);
            Map<String, Object> data = map(response.get("data"));
            Map<String, Object> resultData = map(data.get("result"));
            int extractRows = integer(resultData.get("extract_rows"));
            int storedRows = integer(resultData.get("stored_rows"));

            OperationSyncResult result = OperationSyncResult.success(
                    CURRENCY_SYNC_TYPE, CURRENCY_SYNC_NAME,
                    CURRENCY_API_PATH, extractRows, storedRows,
                    System.currentTimeMillis() - started);
            result.setRequestParams(requestParams);
            result.setDetails(response);
            result.setBusinessSummary(
                    "汇率月份" + resultData.get("rate_month")
                    + "；领星返回" + extractRows + "条"
                    + "；有效币种" + integer(resultData.get("currency_count"))
                    + "个；写入" + storedRows + "条"
                    + "；requestId=" + requestId);
            logService.finish(logId, result);
            OperationSyncContext.set(result);
        }
        catch (Exception e)
        {
            OperationSyncResult failed = OperationSyncResult.failed(
                    CURRENCY_SYNC_TYPE, CURRENCY_SYNC_NAME,
                    CURRENCY_API_PATH,
                    "requestId=" + requestId + "；" + e.getMessage(),
                    System.currentTimeMillis() - started);
            failed.setRequestParams(requestParams);
            Map<String, Object> details = new LinkedHashMap<>();
            details.put("request_id", requestId);
            details.put("stat_month", statMonth);
            details.put("error", e.getMessage());
            failed.setDetails(details);
            logService.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException(
                    "Python领星月度汇率同步失败，requestId="
                    + requestId + "：" + e.getMessage(), e);
        }
    }

    private String currencyRequestParams(
            String statMonth, String requestId)
    {
        try
        {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("stat_month", statMonth);
            params.put("trigger_type", "JOB");
            params.put("request_id", requestId);
            return objectMapper.writeValueAsString(params);
        }
        catch (Exception ignored)
        {
            return "{\"request_id\":\"" + requestId + "\"}";
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value)
    {
        return value instanceof Map<?, ?>
                ? (Map<String, Object>) value
                : Map.of();
    }

    private int integer(Object value)
    {
        if (value instanceof Number) return ((Number) value).intValue();
        try { return Integer.parseInt(String.valueOf(value)); }
        catch (Exception ignored) { return 0; }
    }

    private String requestId()
    {
        return "quartz-monthly-inventory-report-"
                + LocalDateTime.now().format(REQUEST_TIME)
                + "-"
                + UUID.randomUUID().toString().replace("-", "");
    }
}
