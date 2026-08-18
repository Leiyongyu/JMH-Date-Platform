package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 调用仅供后端使用的Python绩效ETL任务接口。 */
@Service
public class PythonPerformanceSchedulerClient extends PythonHttpSupport
{
    private static final String TASK_PREFIX =
            "/api/v1/internal/scheduler/tasks/";
    private static final String PERFORMANCE_TASK =
            "amz_monthly_order_profit_sync";
    private static final String CLEARANCE_TASK =
            "amz_fba_inventory_snapshot_sync";
    private static final String INVENTORY_REPORT_SOURCE_TASK =
            "monthly_inventory_report_source_sync";
    private static final String INVENTORY_REPORT_SALES_VOLUME_TASK =
            "monthly_inventory_report_sales_volume_sync";
    private static final String AMZ_SOP_TASK =
            "amz_sop_after_sales_chain";
    private static final String SERVICE_NAME = "Python绩效ETL";

    public PythonPerformanceSchedulerClient(
            PythonPerformanceTaskProperties properties,
            ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    public Map<String, Object> runPreviousMonth(String requestId)
    {
        return run(PERFORMANCE_TASK, null, requestId);
    }

    public Map<String, Object> run(String statMonth, String requestId)
    {
        return run(PERFORMANCE_TASK, statMonth, requestId);
    }

    public Map<String, Object> runClearance(
            String pullMonth, String requestId)
    {
        return run(CLEARANCE_TASK, pullMonth, requestId);
    }

    public Map<String, Object> runInventoryReportSources(
            String statMonth, String requestId)
    {
        return run(INVENTORY_REPORT_SOURCE_TASK, statMonth, requestId);
    }

    public Map<String, Object> runInventoryReportSalesVolume(
            String statMonth, String requestId)
    {
        return run(INVENTORY_REPORT_SALES_VOLUME_TASK, statMonth, requestId);
    }

    public Map<String, Object> runAmzSop(
            String startDate, String endDate,
            String requestId, String triggerType)
    {
        return run(AMZ_SOP_TASK, null, startDate, endDate,
                requestId, triggerType);
    }

    private Map<String, Object> run(
            String taskCode, String statMonth, String requestId)
    {
        return run(taskCode, statMonth, null, null, requestId, "JOB");
    }

    private Map<String, Object> run(
            String taskCode, String statMonth,
            String startDate, String endDate,
            String requestId, String triggerType)
    {
        try
        {
            Map<String, Object> payload = new LinkedHashMap<>();
            if (AMZ_SOP_TASK.equals(taskCode))
            {
                payload.put("start_date", startDate);
                payload.put("end_date", endDate);
            }
            else if (CLEARANCE_TASK.equals(taskCode)
                    || INVENTORY_REPORT_SOURCE_TASK.equals(taskCode)
                    || INVENTORY_REPORT_SALES_VOLUME_TASK.equals(taskCode))
                payload.put("pull_month", statMonth);
            else
                payload.put("stat_month", statMonth);
            String body = objectMapper.writeValueAsString(payload);
            HttpRequest request = baseRequest(TASK_PREFIX
                    + taskCode + "/run", requestId)
                    .header("Content-Type", "application/json;charset=utf-8")
                    .header("X-Trigger-Type",
                            StringUtils.hasText(triggerType)
                                    ? triggerType : "JOB")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            body, StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            Map<String, Object> json = parseJson(response.body());
            validate(response.statusCode(), json, taskCode);
            return json;
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Python绩效ETL调用被中断", e);
        }
        catch (Exception e)
        {
            if (e instanceof IllegalStateException)
                throw (IllegalStateException) e;
            throw new IllegalStateException(
                    "调用Python绩效ETL失败: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    private void validate(
            int status, Map<String, Object> json, String taskCode)
    {
        if (status != 201)
            throw new IllegalStateException(errorMessage(status, json));
        if (integer(json.get("code"), -1) != 0)
            throw new IllegalStateException(errorMessage(status, json));
        Object dataValue = json.get("data");
        Map<String, Object> data = dataValue instanceof Map<?, ?>
                ? (Map<String, Object>) dataValue : Map.of();
        if (!"completed".equals(String.valueOf(data.get("status"))))
            throw new IllegalStateException(
                    "Python任务未完成: status=" + data.get("status"));
        Object resultValue = data.get("result");
        Map<String, Object> result = resultValue instanceof Map<?, ?>
                ? (Map<String, Object>) resultValue : Map.of();
        if (PERFORMANCE_TASK.equals(taskCode))
        {
            Object refreshValue = result.get("refresh");
            Map<String, Object> refresh = refreshValue instanceof Map<?, ?>
                    ? (Map<String, Object>) refreshValue : Map.of();
            if (!"completed".equals(String.valueOf(refresh.get("status"))))
                throw new IllegalStateException(
                        "Python ETL成功但排名刷新未完成: status="
                        + refresh.get("status"));
        }
    }

    private String errorMessage(int status, Map<String, Object> json)
    {
        Object detail = json.get("detail");
        if (detail != null)
            return SERVICE_NAME + "错误[HTTP " + status + "]: " + detail;
        Object message = json.get("message");
        if (message != null)
            return SERVICE_NAME + "错误[HTTP " + status + "]: " + message;
        return SERVICE_NAME + "请求失败，HTTP " + status;
    }
}
