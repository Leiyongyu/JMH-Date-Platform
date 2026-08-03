package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/** ERP 到 Python 绩效排名 REST 服务的适配客户端。 */
@Service
public class PerformancePythonClient
{
    private static final TypeReference<Map<String, Object>> MAP_TYPE =
            new TypeReference<>() {};

    private final PerformancePythonProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public PerformancePythonClient(
            PerformancePythonProperties properties,
            ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofMillis(
                        properties.getConnectTimeout()))
                .build();
    }

    public Map<String, Object> rankings(
            Map<String, ?> params, String requestId)
    {
        return get("/performance-rankings", params, requestId);
    }

    public Map<String, Object> months(int limit, String requestId)
    {
        return get("/performance-months", Map.of("limit", limit), requestId);
    }

    public Map<String, Object> ownerRuleSummary(
            String platform, String statMonth, String requestId)
    {
        return get("/performance-owner-rule-summaries", Map.of(
                "platform", platform,
                "stat_month", statMonth), requestId);
    }

    public Map<String, Object> clearanceGroups(
            String pullMonth, String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("pull_month", pullMonth);
        return get("/slow-moving-clearance/groups", params, requestId);
    }

    public Map<String, Object> clearanceSummary(
            String pullMonth, String requestId)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("pull_month", pullMonth);
        return get("/slow-moving-clearance/summary", params, requestId);
    }

    public Map<String, Object> clearanceMonths(int limit, String requestId)
    {
        return get("/slow-moving-clearance/months",
                Map.of("limit", limit), requestId);
    }

    public Map<String, Object> refresh(
            String statMonth,
            String platform,
            boolean requireAllPlatforms,
            String requestId)
    {
        try
        {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("stat_month", statMonth);
            payload.put("platform", platform);
            payload.put("require_all_platforms", requireAllPlatforms);
            String json = objectMapper.writeValueAsString(payload);
            HttpRequest request = baseRequest(
                    "/performance-refreshes", requestId)
                    .header("Content-Type", "application/json;charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            json, StandardCharsets.UTF_8))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> importEbayProfit(
            MultipartFile file,
            boolean rebuild,
            String operator,
            String requestId,
            String idempotencyKey)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("rebuild", rebuild);
        params.put("operator", operator);
        return upload(
                "/ebay-profit-imports", params, file,
                requestId, idempotencyKey);
    }

    public Map<String, Object> importOwnerRules(
            String platform,
            MultipartFile file,
            boolean rebuild,
            String statMonth,
            String operator,
            String requestId,
            String idempotencyKey)
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("platform", platform);
        params.put("rebuild", rebuild);
        params.put("stat_month", statMonth);
        params.put("operator", operator);
        return upload(
                "/performance-owner-rule-imports", params, file,
                requestId, idempotencyKey);
    }

    private Map<String, Object> upload(
            String path,
            Map<String, ?> params,
            MultipartFile file,
            String requestId,
            String idempotencyKey)
    {
        try
        {
            if (file == null || file.isEmpty())
                throw new IllegalArgumentException("请选择有效文件");

            String boundary = "----JmhPerformance"
                    + UUID.randomUUID().toString().replace("-", "");
            byte[] body = multipartBody(boundary, file);
            HttpRequest.Builder builder = baseRequest(
                    path + queryString(params), requestId)
                    .header("Content-Type",
                            "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body));
            if (StringUtils.hasText(idempotencyKey))
                builder.header("Idempotency-Key", idempotencyKey);
            return send(builder.build());
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Map<String, Object> get(
            String path, Map<String, ?> params, String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(
                    path + queryString(params), requestId)
                    .GET()
                    .build();
            return send(request, true);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private HttpRequest.Builder baseRequest(String path, String requestId)
    {
        return HttpRequest.newBuilder()
                .uri(URI.create(baseUrl() + path))
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .header("Accept", "application/json")
                .header("X-Request-ID", requestId(requestId));
    }

    private Map<String, Object> send(HttpRequest request)
            throws IOException, InterruptedException
    {
        return send(request, false);
    }

    private Map<String, Object> send(
            HttpRequest request, boolean retryable)
            throws IOException, InterruptedException
    {
        IOException lastException = null;
        for (int attempt = 0; attempt < 3; attempt++)
        {
            try
            {
                HttpResponse<String> response = httpClient.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));
                int status = response.statusCode();
                if (retryable && attempt < 2
                        && (status == 502 || status == 503 || status == 504))
                {
                    retryPause(attempt);
                    continue;
                }
                String body = response.body() == null ? "" : response.body();
                Map<String, Object> json = body.isBlank()
                        ? Map.of()
                        : objectMapper.readValue(body, MAP_TYPE);
                if (status >= 400 || integer(json.get("code"), -1) != 0)
                    throw new IllegalStateException(
                            errorMessage(json, status));
                return json;
            }
            catch (IOException e)
            {
                lastException = e;
                if (!retryable || attempt >= 2) throw e;
                retryPause(attempt);
            }
        }
        throw lastException == null
                ? new IOException("Python绩效服务请求失败")
                : lastException;
    }

    private void retryPause(int attempt) throws InterruptedException
    {
        Thread.sleep(250L * (attempt + 1));
    }

    private byte[] multipartBody(
            String boundary, MultipartFile file) throws IOException
    {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        String filename = file.getOriginalFilename() == null
                ? "upload.xlsx"
                : file.getOriginalFilename().replace("\"", "");
        String contentType = StringUtils.hasText(file.getContentType())
                ? file.getContentType()
                : "application/octet-stream";
        out.write(("--" + boundary + "\r\n")
                .getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Disposition: form-data; name=\"file\"; filename=\""
                + filename + "\"\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Type: " + contentType + "\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));
        out.write(file.getBytes());
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
        out.write(("--" + boundary + "--\r\n")
                .getBytes(StandardCharsets.UTF_8));
        return out.toByteArray();
    }

    private String queryString(Map<String, ?> params)
    {
        if (params == null || params.isEmpty()) return "";
        List<String> parts = new ArrayList<>();
        params.forEach((key, value) -> {
            if (value != null && StringUtils.hasText(String.valueOf(value)))
                parts.add(url(key) + "=" + url(String.valueOf(value)));
        });
        return parts.isEmpty() ? "" : "?" + String.join("&", parts);
    }

    private String errorMessage(Map<String, Object> json, int status)
    {
        Object detail = json.get("detail");
        if (detail != null)
            return "Python绩效服务错误[HTTP " + status + "]: "
                    + stringify(detail);
        Object message = json.get("message");
        if (message != null)
            return "Python绩效服务错误[HTTP " + status + "]: " + message;
        return "Python绩效服务请求失败，HTTP " + status;
    }

    private String stringify(Object value)
    {
        try
        {
            return value instanceof String
                    ? String.valueOf(value)
                    : objectMapper.writeValueAsString(value);
        }
        catch (Exception ignored)
        {
            return String.valueOf(value);
        }
    }

    private int integer(Object value, int defaultValue)
    {
        if (value instanceof Number) return ((Number) value).intValue();
        try
        {
            return Integer.parseInt(String.valueOf(value));
        }
        catch (Exception ignored)
        {
            return defaultValue;
        }
    }

    private String requestId(String value)
    {
        return StringUtils.hasText(value)
                ? value.trim()
                : UUID.randomUUID().toString();
    }

    private String url(String value)
    {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private String baseUrl()
    {
        String value = StringUtils.hasText(properties.getBaseUrl())
                ? properties.getBaseUrl()
                : "http://127.0.0.1:8010/api/v1/finance";
        return value.endsWith("/")
                ? value.substring(0, value.length() - 1)
                : value;
    }

    private RuntimeException asRuntime(Exception e)
    {
        if (e instanceof InterruptedException)
            Thread.currentThread().interrupt();
        if (e instanceof RuntimeException runtimeException)
            return runtimeException;
        return new IllegalStateException(
                "Python绩效服务调用失败: " + e.getMessage(), e);
    }
}
