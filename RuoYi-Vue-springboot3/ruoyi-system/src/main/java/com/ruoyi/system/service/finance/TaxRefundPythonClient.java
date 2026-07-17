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

@Service
public class TaxRefundPythonClient
{
    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {};

    private final TaxRefundPythonProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public TaxRefundPythonClient(TaxRefundPythonProperties properties, ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.getConnectTimeout()))
                .build();
    }

    public Map<String, Object> createJsonTask(Map<String, Object> payload, String erpUser)
    {
        try
        {
            String json = objectMapper.writeValueAsString(payload);
            HttpRequest request = baseRequest("/tasks", erpUser)
                    .header("Content-Type", "application/json;charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> createFileTask(String taskType, MultipartFile file, Map<String, String> fields, String erpUser)
    {
        try
        {
            String boundary = "----JmhTaxRefund" + UUID.randomUUID().toString().replace("-", "");
            byte[] body = multipartBody(boundary, taskType, file, fields);
            HttpRequest request = baseRequest("/tasks", erpUser)
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> createFileTasks(String taskType, MultipartFile[] files, Map<String, String> fields, String erpUser)
    {
        try
        {
            String boundary = "----JmhTaxRefund" + UUID.randomUUID().toString().replace("-", "");
            byte[] body = multipartBody(boundary, taskType, files, fields);
            HttpRequest request = baseRequest("/tasks", erpUser)
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> getTask(Long taskId)
    {
        return get("/tasks/" + taskId, Map.of());
    }

    public Map<String, Object> listTasks(Map<String, ?> params)
    {
        return get("/tasks", params);
    }

    public Map<String, Object> listCustomsMaterialItems(Map<String, ?> params)
    {
        return get("/customs-material-items", params);
    }

    public Map<String, Object> listExportDetails(Map<String, ?> params)
    {
        return get("/export-details", params);
    }

    public Map<String, Object> listPurchaseInventory(Map<String, ?> params)
    {
        return get("/purchase-inventory", params);
    }

    public Map<String, Object> listForexReceivables(Map<String, ?> params)
    {
        return get("/forex-receivables", params);
    }

    private Map<String, Object> get(String path, Map<String, ?> params)
    {
        try
        {
            HttpRequest request = baseRequest(path + queryString(params), null).GET().build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private HttpRequest.Builder baseRequest(String path, String erpUser)
    {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl() + path))
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .header("Accept", "application/json");
        if (StringUtils.hasText(erpUser))
        {
            builder.header("X-ERP-User", erpUser);
        }
        return builder;
    }

    private Map<String, Object> send(HttpRequest request) throws IOException, InterruptedException
    {
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        String body = response.body() == null ? "" : response.body();
        Map<String, Object> json = body.isBlank() ? Map.of() : objectMapper.readValue(body, MAP_TYPE);
        boolean success = Boolean.TRUE.equals(json.get("success"));
        if (response.statusCode() >= 400 || !success)
        {
            throw new IllegalStateException(errorMessage(json, response.statusCode()));
        }
        return json;
    }

    @SuppressWarnings("unchecked")
    private String errorMessage(Map<String, Object> json, int status)
    {
        Object error = json.get("error");
        if (error instanceof Map<?, ?> map)
        {
            Object message = map.get("message");
            Object code = map.get("code");
            if (message != null)
            {
                return "Python退税服务错误[" + status + "/" + code + "]: " + message;
            }
        }
        return "Python退税服务请求失败，HTTP " + status;
    }

    private byte[] multipartBody(String boundary, String taskType, MultipartFile file, Map<String, String> fields) throws IOException
    {
        return multipartBody(boundary, taskType, new MultipartFile[] { file }, fields);
    }

    private byte[] multipartBody(String boundary, String taskType, MultipartFile[] files, Map<String, String> fields) throws IOException
    {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        writeField(out, boundary, "task_type", taskType);
        if (fields != null)
        {
            for (Map.Entry<String, String> entry : fields.entrySet())
            {
                if (StringUtils.hasText(entry.getValue()))
                {
                    writeField(out, boundary, entry.getKey(), entry.getValue());
                }
            }
        }
        int count = 0;
        if (files != null)
        {
            for (MultipartFile file : files)
            {
                if (file != null && !file.isEmpty())
                {
                    writeFile(out, boundary, file);
                    count++;
                }
            }
        }
        if (count == 0)
        {
            throw new IllegalArgumentException("请选择有效文件");
        }
        out.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        return out.toByteArray();
    }

    private void writeField(ByteArrayOutputStream out, String boundary, String name, String value) throws IOException
    {
        out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        out.write((value == null ? "" : value).getBytes(StandardCharsets.UTF_8));
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private void writeFile(ByteArrayOutputStream out, String boundary, MultipartFile file) throws IOException
    {
        String filename = file.getOriginalFilename() == null ? "upload" : file.getOriginalFilename();
        String contentType = StringUtils.hasText(file.getContentType()) ? file.getContentType() : "application/octet-stream";
        out.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Disposition: form-data; name=\"file\"; filename=\"" + filename.replace("\"", "") + "\"\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(("Content-Type: " + contentType + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(file.getBytes());
        out.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private String queryString(Map<String, ?> params)
    {
        if (params == null || params.isEmpty())
        {
            return "";
        }
        List<String> parts = new ArrayList<>();
        params.forEach((key, value) -> {
            if (value != null && StringUtils.hasText(String.valueOf(value)))
            {
                parts.add(url(key) + "=" + url(String.valueOf(value)));
            }
        });
        return parts.isEmpty() ? "" : "?" + String.join("&", parts);
    }

    private String url(String value)
    {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private String baseUrl()
    {
        String baseUrl = StringUtils.hasText(properties.getBaseUrl()) ? properties.getBaseUrl() : "http://127.0.0.1:5000/api/v1";
        return baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
    }

    private RuntimeException asRuntime(Exception e)
    {
        if (e instanceof RuntimeException runtimeException)
        {
            return runtimeException;
        }
        return new IllegalStateException("Python退税服务调用失败: " + e.getMessage(), e);
    }
}
