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

/** Java Quartz 到 Python FBA 库龄 ETL 的调度桥接器。 */
@Component("pythonFbaInventoryTask")
public class PythonFbaInventoryTask
{
    private static final String SYNC_TYPE =
            "python_amz_fba_inventory_etl";
    private static final String SYNC_NAME =
            "Python-AMZ FBA库存库龄ETL";
    private static final String API_PATH =
            "/api/v1/internal/scheduler/tasks/"
            + "amz_fba_inventory_snapshot_sync/run";
    private static final DateTimeFormatter REQUEST_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logService;
    private final ObjectMapper objectMapper;

    public PythonFbaInventoryTask(
            PythonPerformanceSchedulerClient client,
            IOperationSyncLogService logService,
            ObjectMapper objectMapper)
    {
        this.client = client;
        this.logService = logService;
        this.objectMapper = objectMapper;
    }

    public void syncCurrentMonth()
    {
        execute(null);
    }

    /** 供任务页面按月补跑，例如 syncMonth('2026-07')。 */
    public void syncMonth(String pullMonth)
    {
        execute(pullMonth);
    }

    @SuppressWarnings("unchecked")
    private void execute(String pullMonth)
    {
        long started = System.currentTimeMillis();
        String requestId = requestId();
        Long logId = logService.start(
                SYNC_TYPE, SYNC_NAME, API_PATH,
                "JOB", "SYSTEM", null, null);
        String requestParams = requestParams(pullMonth, requestId);
        try
        {
            Map<String, Object> response =
                    client.runClearance(pullMonth, requestId);
            Map<String, Object> data = map(response.get("data"));
            Map<String, Object> resultData = map(data.get("result"));
            int total = integer(resultData.get("extract_rows"));
            int success = integer(resultData.get("dwd_rows"));
            int skipped = integer(resultData.get("unmatched_group_rows"));

            OperationSyncResult result = OperationSyncResult.success(
                    SYNC_TYPE, SYNC_NAME, API_PATH,
                    total, success, System.currentTimeMillis() - started);
            result.setFailCount(skipped);
            result.setRequestParams(requestParams);
            result.setDetails(response);
            result.setBusinessSummary(
                    "月份" + resultData.get("pull_month")
                    + "；领星" + total + "条"
                    + "；DWD写入" + success + "条"
                    + "；DWS分组"
                    + integer(resultData.get("group_rows")) + "条"
                    + "；未匹配" + skipped + "条"
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
            details.put("pull_month", pullMonth);
            details.put("error", e.getMessage());
            failed.setDetails(details);
            logService.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException(
                    "Python FBA库存库龄ETL失败，requestId="
                    + requestId + "：" + e.getMessage(), e);
        }
    }

    private String requestParams(String pullMonth, String requestId)
    {
        try
        {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("pull_month", pullMonth);
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
        return "quartz-fba-inventory-"
                + LocalDateTime.now().format(REQUEST_TIME)
                + "-"
                + UUID.randomUUID().toString().replace("-", "");
    }
}
