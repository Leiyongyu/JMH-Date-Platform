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
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/** Java ERP 到当前 Date-Project 外汇退税 REST 服务的适配客户端。 */
@Service
public class TaxRefundDataProjectClient
{
    private static final TypeReference<Map<String, Object>> MAP_TYPE =
            new TypeReference<>() {};

    private final TaxRefundDataProjectProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public TaxRefundDataProjectClient(
            TaxRefundDataProjectProperties properties,
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

    public Object importCustomsFolder(
            MultipartFile[] files, String erpUser)
    {
        return upload("/api/import-jobs/customs-folder",
                "files", files, erpUser);
    }

    public Object importPurchaseInvoice(
            MultipartFile file, String erpUser)
    {
        return upload("/api/upload/purchase-invoice-summary",
                "file", new MultipartFile[] { file }, erpUser);
    }

    public Object importForeignExchange(
            MultipartFile file, String erpUser)
    {
        return upload("/api/upload/foreign-exchange-receipts",
                "file", new MultipartFile[] { file }, erpUser);
    }

    public Object getImportJob(String jobId)
    {
        return get("/api/import-jobs/" + url(jobId), Map.of());
    }

    public Object customsDeclarations()
    {
        return get("/api/customs-declarations/options", Map.of());
    }

    public Object createDeclarationBatch(Map<String, Object> payload)
    {
        return postJson(
                "/api/customs-declarations/batch-convert-to-export-details",
                payload);
    }

    public Object generatePackage(Map<String, Object> payload)
    {
        return postJson("/api/export/final-package",
                payload == null ? Map.of() : payload);
    }

    public Map<String, Object> inventory(Map<String, ?> params)
    {
        Object response = get("/api/inventory", params);
        if (!(response instanceof Map<?, ?> raw))
            throw new IllegalStateException("Python库存接口响应格式错误");
        @SuppressWarnings("unchecked")
        Map<String, Object> map = (Map<String, Object>) raw;
        return map;
    }

    public byte[] downloadLatestPackage()
    {
        try
        {
            HttpRequest request = baseRequest(
                    "/api/export/download-package", null)
                    .GET()
                    .build();
            HttpResponse<byte[]> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() >= 400)
            {
                String text = new String(
                        response.body(), StandardCharsets.UTF_8);
                throw new IllegalStateException(
                        errorMessage(text, response.statusCode()));
            }
            return response.body();
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Object upload(
            String path,
            String fieldName,
            MultipartFile[] files,
            String erpUser)
    {
        try
        {
            String boundary = "----JmhDateProject"
                    + UUID.randomUUID().toString().replace("-", "");
            byte[] body = multipartBody(boundary, fieldName, files);
            HttpRequest request = baseRequest(path, erpUser)
                    .header("Content-Type",
                            "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Object postJson(String path, Map<String, Object> payload)
    {
        try
        {
            String body = objectMapper.writeValueAsString(
                    payload == null ? Map.of() : payload);
            HttpRequest request = baseRequest(path, null)
                    .header("Content-Type",
                            "application/json;charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            body, StandardCharsets.UTF_8))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Object get(String path, Map<String, ?> params)
    {
        try
        {
            HttpRequest request = baseRequest(
                    path + queryString(params), null)
                    .GET()
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Object send(HttpRequest request)
            throws IOException, InterruptedException
    {
        HttpResponse<String> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        String body = response.body() == null ? "" : response.body();
        if (response.statusCode() >= 400)
            throw new IllegalStateException(
                    errorMessage(body, response.statusCode()));
        Object json = body.isBlank()
                ? Map.of()
                : objectMapper.readValue(body, Object.class);
        if (json instanceof Map<?, ?> map && map.containsKey("code")
                && integer(map.get("code"), -1) != 0)
        {
            Object message = map.get("message");
            throw new IllegalStateException(
                    "Python外汇退税服务错误: "
                    + (message == null ? "unknown" : message));
        }
        return json;
    }

    private HttpRequest.Builder baseRequest(String path, String erpUser)
    {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl() + path))
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .header("Accept", "application/json");
        if (StringUtils.hasText(erpUser))
            builder.header("X-ERP-User", erpUser);
        return builder;
    }

    private byte[] multipartBody(
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

    private String errorMessage(String body, int status)
    {
        try
        {
            Map<String, Object> json = objectMapper.readValue(body, MAP_TYPE);
            Object detail = json.get("detail");
            if (detail != null)
                return "Python外汇退税服务错误[HTTP "
                        + status + "]: " + detail;
        }
        catch (Exception ignored)
        {
        }
        return "Python外汇退税服务请求失败，HTTP " + status;
    }

    private int integer(Object value, int defaultValue)
    {
        if (value instanceof Number) return ((Number) value).intValue();
        try { return Integer.parseInt(String.valueOf(value)); }
        catch (Exception ignored) { return defaultValue; }
    }

    private String url(String value)
    {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private String baseUrl()
    {
        String value = StringUtils.hasText(properties.getBaseUrl())
                ? properties.getBaseUrl()
                : "http://127.0.0.1:8010";
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
                "Python外汇退税服务调用失败: " + e.getMessage(), e);
    }
}
