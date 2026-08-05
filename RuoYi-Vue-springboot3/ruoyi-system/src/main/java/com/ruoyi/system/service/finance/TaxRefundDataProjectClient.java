package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/** Java ERP 到当前 Date-Project 外汇退税 REST 服务的适配客户端。 */
@Service
public class TaxRefundDataProjectClient extends PythonHttpSupport
{
    private static final String SERVICE_NAME = "Python外汇退税服务";

    public TaxRefundDataProjectClient(
            TaxRefundDataProjectProperties properties,
            ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
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
                    SERVICE_NAME + "错误: "
                    + (message == null ? "unknown" : message));
        }
        return json;
    }

    private String errorMessage(String body, int status)
    {
        try
        {
            Map<String, Object> json = objectMapper.readValue(body, MAP_TYPE);
            Object detail = json.get("detail");
            if (detail != null)
                return SERVICE_NAME + "错误[HTTP "
                        + status + "]: " + detail;
        }
        catch (Exception ignored)
        {
        }
        return SERVICE_NAME + "请求失败，HTTP " + status;
    }
}
