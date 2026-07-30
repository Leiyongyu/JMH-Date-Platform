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

/** Java Quartz到Python绩效ETL的唯一调度桥接器。 */
@Component("pythonPerformanceTask")
public class PythonPerformanceTask
{
    private static final String SYNC_TYPE =
            "python_amz_monthly_profit_etl";
    private static final String SYNC_NAME =
            "Python-AMZ月度利润ETL";
    private static final String API_PATH =
            "/api/v1/internal/scheduler/tasks/"
            + "amz_monthly_order_profit_sync/run";
    private static final DateTimeFormatter REQUEST_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logService;
    private final ObjectMapper objectMapper;

    public PythonPerformanceTask(
            PythonPerformanceSchedulerClient client,
            IOperationSyncLogService logService,
            ObjectMapper objectMapper)
    {
        this.client = client;
        this.logService = logService;
        this.objectMapper = objectMapper;
    }

    public void syncPreviousMonth()
    {
        execute(null);
    }

    /** 供若依任务页面按月手工补跑，例如syncMonth('2026-06')。 */
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
            Map<String, Object> response = statMonth == null
                    ? client.runPreviousMonth(requestId)
                    : client.run(statMonth, requestId);
            Map<String, Object> data = map(response.get("data"));
            Map<String, Object> resultData = map(data.get("result"));
            Map<String, Object> refresh = map(resultData.get("refresh"));

            int total = integer(resultData.get("extract_rows"));
            int success = integer(resultData.get("dwd_rows"));
            int skipped = integer(resultData.get("skipped_rows"));
            OperationSyncResult result = OperationSyncResult.success(
                    SYNC_TYPE, SYNC_NAME, API_PATH,
                    total, success,
                    System.currentTimeMillis() - started);
            result.setFailCount(skipped);
            result.setRequestParams(requestParams);
            result.setDetails(response);
            result.setBusinessSummary(summary(
                    requestId, resultData, refresh));

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
                    "Python AMZ月利润ETL失败，requestId="
                    + requestId + "：" + e.getMessage(), e);
        }
    }

    private String summary(
            String requestId,
            Map<String, Object> result,
            Map<String, Object> refresh)
    {
        return "月份" + result.get("stat_month")
                + "；领星" + integer(result.get("extract_rows")) + "条"
                + "；DWD写入" + integer(result.get("dwd_rows")) + "条"
                + "；AMZ排名"
                + integer(refresh.get("amz_ranking_rows")) + "条"
                + "；综合排名"
                + integer(refresh.get("combined_ranking_rows")) + "条"
                + "；requestId=" + requestId;
    }

    private String requestParams(String statMonth, String requestId)
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
        return "quartz-amz-profit-"
                + LocalDateTime.now().format(REQUEST_TIME)
                + "-"
                + UUID.randomUUID().toString().replace("-", "");
    }
}
