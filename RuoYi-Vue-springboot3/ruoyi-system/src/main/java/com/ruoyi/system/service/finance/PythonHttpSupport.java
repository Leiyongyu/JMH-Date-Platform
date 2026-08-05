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
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/**
 * Python 内网服务 HTTP 客户端公共基类。
 * 统一超时、X-Request-ID、X-Internal-Token 与错误解析，子类只保留各自的业务语义。
 */
public abstract class PythonHttpSupport
{
    /** 请求头名称，与 Python 端 RequestIdMiddleware 对齐。 */
    public static final String REQUEST_ID_HEADER = "X-Request-ID";
    /** MDC 键，与 Python 日志字段 request_id 对齐。 */
    public static final String REQUEST_ID_MDC_KEY = "request_id";

    private static final String TOKEN_HEADER = "X-Internal-Token";

    protected static final TypeReference<Map<String, Object>> MAP_TYPE =
            new TypeReference<>() {};

    protected final ObjectMapper objectMapper;
    protected final HttpClient httpClient;
    private final PythonServiceProperties properties;

    protected PythonHttpSupport(
            PythonServiceProperties properties,
            ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofMillis(
                        properties.getConnectTimeoutMillis()))
                .build();
    }

    protected String baseUrl()
    {
        String value = properties.getBaseUrl();
        return value.endsWith("/")
                ? value.substring(0, value.length() - 1)
                : value;
    }

    protected HttpRequest.Builder baseRequest(String path, String requestId)
    {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl() + path))
                .timeout(Duration.ofMillis(properties.getReadTimeoutMillis()))
                .header("Accept", "application/json")
                .header(REQUEST_ID_HEADER, effectiveRequestId(requestId));
        String token = properties.getInternalToken();
        if (StringUtils.hasText(token))
            builder.header(TOKEN_HEADER, token);
        return builder;
    }

    protected String effectiveRequestId(String value)
    {
        if (StringUtils.hasText(value))
            return value.trim();
        String mdcId = MDC.get(REQUEST_ID_MDC_KEY);
        if (StringUtils.hasText(mdcId))
            return mdcId.trim();
        return UUID.randomUUID().toString();
    }

    protected String queryString(Map<String, ?> params)
    {
        if (params == null || params.isEmpty()) return "";
        List<String> parts = new ArrayList<>();
        params.forEach((key, value) -> {
            if (value != null && StringUtils.hasText(String.valueOf(value)))
                parts.add(url(key) + "=" + url(String.valueOf(value)));
        });
        return parts.isEmpty() ? "" : "?" + String.join("&", parts);
    }

    protected String url(String value)
    {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    protected Map<String, Object> parseJson(String body) throws Exception
    {
        if (!StringUtils.hasText(body)) return Map.of();
        return objectMapper.readValue(body, MAP_TYPE);
    }

    protected String errorMessage(Map<String, Object> json, int status, String serviceName)
    {
        Object detail = json.get("detail");
        if (detail != null)
            return serviceName + "错误[HTTP " + status + "]: " + stringify(detail);
        Object message = json.get("message");
        if (message != null)
            return serviceName + "错误[HTTP " + status + "]: " + message;
        return serviceName + "请求失败，HTTP " + status;
    }

    protected String stringify(Object value)
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

    protected int integer(Object value, int defaultValue)
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

    protected RuntimeException asRuntime(Exception e)
    {
        if (e instanceof InterruptedException)
            Thread.currentThread().interrupt();
        if (e instanceof RuntimeException runtimeException)
            return runtimeException;
        return new IllegalStateException(
                "Python服务调用失败: " + e.getMessage(), e);
    }

    /** 统一 multipart 组装；空文件跳过，全部为空时抛异常。 */
    protected byte[] multipartBody(
            String boundary,
            String fieldName,
            MultipartFile[] files) throws IOException
    {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int count = 0;
        if (files != null)
        {
            for (MultipartFile file : files)
            {
                if (file == null || file.isEmpty()) continue;
                String filename = file.getOriginalFilename() == null
                        ? "upload.xlsx"
                        : file.getOriginalFilename().replace("\"", "");
                String contentType = StringUtils.hasText(file.getContentType())
                        ? file.getContentType()
                        : "application/octet-stream";
                out.write(("--" + boundary + "\r\n")
                        .getBytes(StandardCharsets.UTF_8));
                out.write(("Content-Disposition: form-data; name=\""
                        + fieldName + "\"; filename=\"" + filename
                        + "\"\r\n").getBytes(StandardCharsets.UTF_8));
                out.write(("Content-Type: " + contentType + "\r\n\r\n")
                        .getBytes(StandardCharsets.UTF_8));
                out.write(file.getBytes());
                out.write("\r\n".getBytes(StandardCharsets.UTF_8));
                count++;
            }
        }
        if (count == 0)
            throw new IllegalArgumentException("请选择有效文件");
        out.write(("--" + boundary + "--\r\n")
                .getBytes(StandardCharsets.UTF_8));
        return out.toByteArray();
    }
}
