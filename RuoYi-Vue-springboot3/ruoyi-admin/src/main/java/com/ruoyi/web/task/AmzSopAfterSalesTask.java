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

/** 每周串行触发Python的AMZ订单利润、售后订单及分类汇总链路。 */
@Component("amzSopAfterSalesTask")
public class AmzSopAfterSalesTask
{
    private static final String SYNC_TYPE = "amz_sop_after_sales_chain";
    private static final String SYNC_NAME = "AMZ-SOP售后链路";
    private static final String API_PATH =
            "/api/v1/internal/scheduler/tasks/amz_sop_after_sales_chain/run";
    private static final DateTimeFormatter REQUEST_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final PythonPerformanceSchedulerClient client;
    private final IOperationSyncLogService logService;
    private final ObjectMapper objectMapper;

    public AmzSopAfterSalesTask(
            PythonPerformanceSchedulerClient client,
            IOperationSyncLogService logService,
            ObjectMapper objectMapper)
    {
        this.client = client;
        this.logService = logService;
        this.objectMapper = objectMapper;
    }

    public void runWeekly()
    {
        execute(null, null);
    }

    /** 若依任务页面可按日期补跑，例如runRange('2026-06-01','2026-06-30')。 */
    public void runRange(String startDate, String endDate)
    {
        execute(startDate, endDate);
    }

    @SuppressWarnings("unchecked")
    private void execute(String startDate, String endDate)
    {
        long started = System.currentTimeMillis();
        String requestId = "quartz-amz-sop-"
                + LocalDateTime.now().format(REQUEST_TIME) + "-"
                + UUID.randomUUID().toString().replace("-", "");
        Long logId = logService.start(
                SYNC_TYPE, SYNC_NAME, API_PATH,
                "JOB", "SYSTEM", null, null);
        try
        {
            Map<String, Object> response = client.runAmzSop(
                    startDate, endDate, requestId, "JOB");
            Map<String, Object> data = map(response.get("data"));
            Map<String, Object> resultData = map(data.get("result"));
            OperationSyncResult result = OperationSyncResult.success(
                    SYNC_TYPE, SYNC_NAME, API_PATH,
                    integer(resultData.get("extract_rows")),
                    integer(resultData.get("dwd_rows")),
                    System.currentTimeMillis() - started);
            result.setFailCount(integer(resultData.get("skipped_rows")));
            result.setRequestParams(params(startDate, endDate, requestId));
            result.setDetails(response);
            result.setBusinessSummary(
                    "区间" + resultData.get("period_start") + "至"
                    + resultData.get("period_end")
                    + "；销量源" + integer(resultData.get("sales_extract_rows")) + "条"
                    + "；售后明细" + integer(resultData.get("after_sales_dwd_rows")) + "条"
                    + "；汇总" + integer(resultData.get("summary_rows")) + "条"
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
            failed.setRequestParams(params(startDate, endDate, requestId));
            logService.finish(logId, failed);
            OperationSyncContext.set(failed);
            throw new IllegalStateException(
                    SYNC_NAME + "失败，requestId=" + requestId + "："
                    + e.getMessage(), e);
        }
    }

    private String params(String startDate, String endDate, String requestId)
    {
        try
        {
            Map<String, Object> values = new LinkedHashMap<>();
            values.put("start_date", startDate);
            values.put("end_date", endDate);
            values.put("request_id", requestId);
            return objectMapper.writeValueAsString(values);
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
                ? (Map<String, Object>) value : Map.of();
    }

    private int integer(Object value)
    {
        if (value instanceof Number) return ((Number) value).intValue();
        try { return Integer.parseInt(String.valueOf(value)); }
        catch (Exception ignored) { return 0; }
    }
}
