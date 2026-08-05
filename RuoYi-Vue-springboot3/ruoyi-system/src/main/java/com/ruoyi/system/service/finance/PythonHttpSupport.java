package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.SequenceInputStream;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/**
 * Base support for internal Python HTTP clients.
 * Keeps timeout, request id, token, query string, error parsing and multipart
 * behavior consistent across finance, scheduler and tax-refund clients.
 */
public abstract class PythonHttpSupport
{
    public static final String REQUEST_ID_HEADER = "X-Request-ID";
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

    protected HttpRequest.BodyPublisher multipartBodyPublisher(
            String boundary,
            String fieldName,
            MultipartFile[] files)
    {
        List<MultipartFile> validFiles = new ArrayList<>();
        if (files != null)
            for (MultipartFile file : files)
                if (file != null && !file.isEmpty())
                    validFiles.add(file);
        if (validFiles.isEmpty())
            throw new IllegalArgumentException("请选择有效文件");
        return HttpRequest.BodyPublishers.ofInputStream(
                () -> multipartInputStream(boundary, fieldName, validFiles));
    }

    private InputStream multipartInputStream(
            String boundary,
            String fieldName,
            List<MultipartFile> files)
    {
        try
        {
            List<InputStream> streams = new ArrayList<>();
            for (MultipartFile file : files)
            {
                streams.add(textStream(partHeader(boundary, fieldName, file)));
                streams.add(file.getInputStream());
                streams.add(textStream("\r\n"));
            }
            streams.add(textStream("--" + boundary + "--\r\n"));
            return new SequenceInputStream(Collections.enumeration(streams));
        }
        catch (IOException e)
        {
            throw new UncheckedIOException(e);
        }
    }

    private String partHeader(
            String boundary,
            String fieldName,
            MultipartFile file)
    {
        String filename = file.getOriginalFilename() == null
                ? "upload.xlsx"
                : file.getOriginalFilename().replace("\"", "");
        String contentType = StringUtils.hasText(file.getContentType())
                ? file.getContentType()
                : "application/octet-stream";
        return "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + fieldName
                + "\"; filename=\"" + filename + "\"\r\n"
                + "Content-Type: " + contentType + "\r\n\r\n";
    }

    private InputStream textStream(String value)
    {
        return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
    }
}
