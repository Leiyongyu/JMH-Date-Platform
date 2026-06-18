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
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class LingxingOpenApiClient
{
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

    public Map<String, Object> postForm(String path, Map<String, String> query) throws Exception
    {
        URI uri = buildUri(path, query);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        return execute(request);
    }

    public Map<String, Object> postJson(String path, Map<String, Object> body) throws Exception
    {
        HttpRequest request = HttpRequest.newBuilder(buildUri(path, null))
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .header("Content-Type", "application/json;charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body), StandardCharsets.UTF_8))
                .build();
        return execute(request);
    }

    private Map<String, Object> execute(HttpRequest request) throws Exception
    {
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (response.statusCode() < 200 || response.statusCode() >= 300)
        {
            throw new IllegalStateException("Lingxing HTTP " + response.statusCode() + ": " + response.body());
        }
        return objectMapper.readValue(response.body(), new TypeReference<Map<String, Object>>() {});
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
