package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 调用仅供后端使用的Python绩效ETL任务接口。 */
@Service
public class PythonPerformanceSchedulerClient
{
    private static final String TASK_PATH =
            "/api/v1/internal/scheduler/tasks/"
            + "amz_monthly_order_profit_sync/run";
    private static final TypeReference<Map<String, Object>> MAP_TYPE =
            new TypeReference<>() {};

    private final PythonPerformanceTaskProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public PythonPerformanceSchedulerClient(
            PythonPerformanceTaskProperties properties,
            ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(properties.getConnectTimeout())
                .build();
    }

    public Map<String, Object> runPreviousMonth(String requestId)
    {
        return run(null, requestId);
    }

    public Map<String, Object> run(String statMonth, String requestId)
    {
        try
        {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("stat_month", statMonth);
            String body = objectMapper.writeValueAsString(payload);
            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl() + TASK_PATH))
                    .timeout(properties.getReadTimeout())
                    .header("Accept", "application/json")
                    .header("Content-Type", "application/json;charset=utf-8")
                    .header("X-Request-ID", requestId)
                    .header("X-Trigger-Type", "JOB")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            body, StandardCharsets.UTF_8));
            if (StringUtils.hasText(properties.getInternalToken()))
                builder.header("X-Internal-Token",
                        properties.getInternalToken());

            HttpResponse<String> response = httpClient.send(
                    builder.build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            Map<String, Object> json = parse(response.body());
            validate(response.statusCode(), json);
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
    private void validate(int status, Map<String, Object> json)
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
        Object refreshValue = result.get("refresh");
        Map<String, Object> refresh = refreshValue instanceof Map<?, ?>
                ? (Map<String, Object>) refreshValue : Map.of();
        if (!"completed".equals(String.valueOf(refresh.get("status"))))
            throw new IllegalStateException(
                    "Python ETL成功但排名刷新未完成: status="
                    + refresh.get("status"));
    }

    private Map<String, Object> parse(String body) throws Exception
    {
        if (!StringUtils.hasText(body)) return Map.of();
        return objectMapper.readValue(body, MAP_TYPE);
    }

    private String errorMessage(int status, Map<String, Object> json)
    {
        Object detail = json.get("detail");
        if (detail != null)
            return "Python绩效ETL错误[HTTP " + status + "]: " + detail;
        Object message = json.get("message");
        if (message != null)
            return "Python绩效ETL错误[HTTP " + status + "]: " + message;
        return "Python绩效ETL请求失败，HTTP " + status;
    }

    private int integer(Object value, int defaultValue)
    {
        if (value instanceof Number) return ((Number) value).intValue();
        try { return Integer.parseInt(String.valueOf(value)); }
        catch (Exception ignored) { return defaultValue; }
    }

    private String baseUrl()
    {
        String value = properties.getBaseUrl();
        return value.endsWith("/")
                ? value.substring(0, value.length() - 1)
                : value;
    }
}
