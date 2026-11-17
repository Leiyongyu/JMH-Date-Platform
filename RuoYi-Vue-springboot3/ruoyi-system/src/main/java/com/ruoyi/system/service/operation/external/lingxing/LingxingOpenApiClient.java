package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class LingxingOpenApiClient
{
    private static final Logger LOG = LoggerFactory.getLogger(LingxingOpenApiClient.class);
    private static final int MAX_RETRIES = 3;
    private static final long RETRY_BASE_DELAY_MS = 1000;

    private final LingxingProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public LingxingOpenApiClient(LingxingProperties properties, ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.getConnectTimeout()))
                .build();
    }

    public Map<String, Object> postSigned(String path, Map<String, Object> body, String accessToken) throws Exception
    {
        Map<String, Object> params = new LinkedHashMap<>();
        if (body != null)
        {
            params.putAll(body);
        }
        params.put("timestamp", String.valueOf(System.currentTimeMillis() / 1000));
        params.put("access_token", accessToken);
        params.put("app_key", properties.getAppId());
        params.put("sign", LingxingSignUtils.sign(params, properties.getAppId()));
        return postJson(path, params);
    }

    /**
     * 鉴权参数放 query string、业务参数放 JSON body 的签名请求。
     * 对齐旧项目 {@code callWarehouseApi()} 的调用方式：
     * query string: timestamp, access_token, app_key, sign
     * body: 业务参数（type, is_delete, offset, length 等）
     * sign 基于 query + body 全部参数的并集计算。
     */
    public Map<String, Object> postSignedQueryAuth(String path, Map<String, Object> body, String accessToken) throws Exception
    {
        // 1. 构建 query 参数
        Map<String, String> queryParams = new LinkedHashMap<>();
        String timestamp = String.valueOf(System.currentTimeMillis() / 1000);
        queryParams.put("timestamp", timestamp);
        queryParams.put("access_token", accessToken);
        queryParams.put("app_key", properties.getAppId());

        // 2. 构建签名参数集 = query 参数 + body 参数
        Map<String, Object> signParams = new LinkedHashMap<>();
        signParams.put("timestamp", timestamp);
        signParams.put("access_token", accessToken);
        signParams.put("app_key", properties.getAppId());
        if (body != null)
        {
            signParams.putAll(body);
        }
        String sign = LingxingSignUtils.sign(signParams, properties.getAppId());
        queryParams.put("sign", sign);

        // 3. 发送请求：query 参数拼接到 URL，body 作为 JSON
        String jsonBody = body != null ? objectMapper.writeValueAsString(body) : "{}";
        URI uri = buildUri(path, queryParams);

        return execute(() -> HttpRequest.newBuilder(uri)
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .header("Content-Type", "application/json;charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                .build());
    }

    public Map<String, Object> postForm(String path, Map<String, String> query) throws Exception
    {
        URI uri = buildUri(path, query);
        return execute(() -> HttpRequest.newBuilder(uri)
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build());
    }

    public Map<String, Object> postJson(String path, Map<String, Object> body) throws Exception
    {
        URI uri = buildUri(path, null);
        byte[] bodyBytes = objectMapper.writeValueAsBytes(body);
        return execute(() -> HttpRequest.newBuilder(uri)
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .header("Content-Type", "application/json;charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofByteArray(bodyBytes))
                .build());
    }

    /**
     * Execute with retry on 5xx and I/O errors. {@code requestSupplier} is called
     * on every retry to produce a fresh {@link HttpRequest} (BodyPublisher is single-use).
     */
    private Map<String, Object> execute(Supplier<HttpRequest> requestSupplier) throws Exception
    {
        Exception lastEx = null;
        for (int attempt = 0; attempt <= MAX_RETRIES; attempt++)
        {
            if (attempt > 0)
            {
                long delay = RETRY_BASE_DELAY_MS * (1L << (attempt - 1)); // 1s, 2s, 4s
                LOG.warn("Lingxing API retry {}/{} after {}ms", attempt, MAX_RETRIES, delay);
                Thread.sleep(delay);
            }
            HttpRequest request = requestSupplier.get();
            try
            {
                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                int code = response.statusCode();
                if (code >= 200 && code < 300)
                {
                    return objectMapper.readValue(response.body(), new TypeReference<Map<String, Object>>() {});
                }
                // 4xx = client error, don't retry
                if (code >= 400 && code < 500)
                {
                    throw new IllegalStateException("Lingxing HTTP " + code + ": " + response.body());
                }
                lastEx = new IllegalStateException("Lingxing HTTP " + code + ": " + response.body());
                LOG.warn("Lingxing API returned {} (attempt {}/{})", code, attempt + 1, MAX_RETRIES + 1);
            }
            catch (IllegalStateException e)
            {
                throw e; // 4xx — rethrow immediately
            }
            catch (Exception e)
            {
                lastEx = e;
                LOG.warn("Lingxing API I/O error (attempt {}/{}): {}", attempt + 1, MAX_RETRIES + 1, e.getMessage());
            }
        }
        throw lastEx != null ? lastEx : new IllegalStateException("Lingxing API retry exhausted");
    }

    private URI buildUri(String path, Map<String, String> query)
    {
        String endpoint = trimRight(properties.getEndpoint(), "/");
        String normalizedPath = trimLeft(path, "/");
        StringBuilder uri = new StringBuilder(endpoint).append("/").append(normalizedPath);
        if (query != null && !query.isEmpty())
        {
            uri.append("?");
            boolean first = true;
            for (Map.Entry<String, String> entry : query.entrySet())
            {
                if (!first)
                {
                    uri.append("&");
                }
                first = false;
                uri.append(encode(entry.getKey())).append("=").append(encode(entry.getValue()));
            }
        }
        return URI.create(uri.toString());
    }

    private String encode(String value)
    {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }

    private String trimLeft(String value, String token)
    {
        String result = StringUtils.hasText(value) ? value.trim() : "";
        while (result.startsWith(token))
        {
            result = result.substring(token.length());
        }
        return result;
    }

    private String trimRight(String value, String token)
    {
        String result = StringUtils.hasText(value) ? value.trim() : "";
        while (result.endsWith(token))
        {
            result = result.substring(0, result.length() - token.length());
        }
        return result;
    }
}
