package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/** ERP 到 Python 绩效排名 REST 服务的适配客户端。 */
@Service
public class PerformancePythonClient extends PythonHttpSupport
{
    private static final String SERVICE_NAME = "Python绩效服务";

    public PerformancePythonClient(
            PerformancePythonProperties properties,
            ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
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
            return sendJson(request, false);
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
            HttpRequest.BodyPublisher body = multipartBodyPublisher(boundary, "file",
                    new MultipartFile[] { file });
            HttpRequest.Builder builder = baseRequest(
                    path + queryString(params), requestId)
                    .header("Content-Type",
                            "multipart/form-data; boundary=" + boundary)
                    .POST(body);
            if (StringUtils.hasText(idempotencyKey))
                builder.header("Idempotency-Key", idempotencyKey);
            return sendJson(builder.build(), false);
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
            return sendJson(request, true);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    /** GET 查询类接口在网关层（502/503/504）与网络异常时重试，写操作不重试。 */
    private Map<String, Object> sendJson(
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
                            errorMessage(json, status, SERVICE_NAME));
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
                ? new IOException(SERVICE_NAME + "请求失败")
                : lastException;
    }

    private void retryPause(int attempt) throws InterruptedException
    {
        Thread.sleep(250L * (attempt + 1));
    }
}
