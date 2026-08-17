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
            "Python-月度库存报表拉取清洗汇总";
    private static final String API_PATH =
            "/api/v1/internal/scheduler/tasks/"
            + "monthly_inventory_report_source_sync/run";
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

    /** 每月定时任务默认拉取上一个完整自然月。 */
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

    @SuppressWarnings("unchecked")
    private void execute(String statMonth)
    {
        long started = System.currentTimeMillis();
        String requestId = requestId();
        Long logId = logService.start(
                SYNC_TYPE, SYNC_NAME, API_PATH,
                "JOB", "SYSTEM", null, null);
        String requestParams = requestParams(statMonth, requestId);
        try
        {
            Map<String, Object> response =
                    client.runInventoryReportSources(statMonth, requestId);
            Map<String, Object> data = map(response.get("data"));
            Map<String, Object> resultData = map(data.get("result"));
            int fbaRows = integer(resultData.get("fba_rows"));
            int overseasRows = integer(resultData.get("overseas_rows"));
            int localRows = integer(resultData.get("local_rows"));
            int dwdRows = integer(resultData.get("dwd_rows"));
            int summaryRows = integer(resultData.get("summary_rows"));
            int total = integer(resultData.get("extract_rows"));

            OperationSyncResult result = OperationSyncResult.success(
                    SYNC_TYPE, SYNC_NAME, API_PATH,
                    total, integer(resultData.get("ods_rows")),
                    System.currentTimeMillis() - started);
            result.setRequestParams(requestParams);
            result.setDetails(response);
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
                    SYNC_TYPE, SYNC_NAME, API_PATH,
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
                    "Python月度库存报表源数据同步失败，requestId="
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
