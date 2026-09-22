package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.finance.PythonHttpSupport;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

/** ERP 到 Python 库存明细服务；复用内部 Token、请求 ID 和上传流。 */
@Service
public class EbayInventoryDetailPythonClient extends PythonHttpSupport
{
    public static final String EXCEL_CONTENT_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final String PREFIX = "/ebay-inventory-detail";
    private static final String SERVICE_NAME = "Python eBay库存明细服务";

    public EbayInventoryDetailPythonClient(PerformancePythonProperties properties, ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    public Map<String, Object> list(Map<String, ?> params, String requestId)
    {
        try
        {
            return sendJson(baseRequest(PREFIX + "/list" + queryString(params), requestId).GET().build());
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> pivot(Map<String, ?> params, String requestId)
    {
        try
        {
            return sendJson(baseRequest(PREFIX + "/pivot" + queryString(params), requestId).GET().build());
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> recalculateSnapshot(String requestId)
    {
        try
        {
            return sendJson(baseRequest(PREFIX + "/snapshot/recalculate", requestId)
                    .POST(HttpRequest.BodyPublishers.noBody()).build());
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> importPrices(MultipartFile file, String operator, String requestId)
    {
        return importFile("/prices/import", "产品单价", file, operator, requestId);
    }

    private Map<String, Object> importFile(String path, String label, MultipartFile file,
            String operator, String requestId)
    {
        return importFile(path, label, file, operator, requestId, 10);
    }

    public Map<String, Object> importHistory(MultipartFile file, String operator, String requestId)
    {
        return importFile("/history/import", "库存历史", file, operator, requestId, 50);
    }

    private Map<String, Object> importFile(String path, String label, MultipartFile file,
            String operator, String requestId, int maxMb)
    {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("请选择有效的" + label + "文件");
        if (file.getSize() > (long) maxMb * 1024 * 1024)
            throw new IllegalArgumentException(label + "文件不能超过" + maxMb + "MB");
        try
        {
            String boundary = "----EbayInventoryImport" + UUID.randomUUID().toString().replace("-", "");
            HttpRequest.Builder builder = baseRequest(PREFIX + path
                            + queryString(Map.of("operator", operator)), requestId);
            if ("/history/import".equals(path)) builder.timeout(java.time.Duration.ofSeconds(300));
            HttpRequest request = builder
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(multipartBodyPublisher(boundary, "file", new MultipartFile[] { file }))
                    .build();
            return sendJson(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public ExcelFile export(Map<String, ?> payload, String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(PREFIX + "/export", requestId)
                    .setHeader("Accept", EXCEL_CONTENT_TYPE)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            objectMapper.writeValueAsString(payload), StandardCharsets.UTF_8))
                    .build();
            return sendExcel(request, "Ebay库存明细-", "ebay-inventory-detail.xlsx");
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public ExcelFile exportPivot(Map<String, ?> params, String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(PREFIX + "/pivot/export" + queryString(params), requestId)
                    .setHeader("Accept", EXCEL_CONTENT_TYPE)
                    .GET().build();
            return sendExcel(request, "Ebay库存历史透视-", "ebay-inventory-pivot.xlsx");
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private ExcelFile sendExcel(HttpRequest request, String filenamePrefix, String fallbackFilename)
            throws Exception
    {
        HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
        String contentType = response.headers().firstValue("Content-Type").orElse("");
        if (response.statusCode() >= 400 || contentType.toLowerCase(java.util.Locale.ROOT).contains("json"))
        {
            throw new IllegalStateException(errorMessage(parseJson(
                    new String(response.body(), StandardCharsets.UTF_8)), response.statusCode(), SERVICE_NAME));
        }
        if (response.statusCode() != 200 || !contentType.startsWith(EXCEL_CONTENT_TYPE))
            throw new IllegalStateException(SERVICE_NAME + "未返回有效的Excel文件");

        String disposition = response.headers().firstValue("Content-Disposition").orElse("");
        if (!disposition.startsWith("attachment;") || disposition.contains("\r") || disposition.contains("\n"))
        {
            String filename = filenamePrefix + LocalDateTime.now()
                    .format(DateTimeFormatter.ofPattern("yyyyMMddHHmmss")) + ".xlsx";
            disposition = "attachment; filename=" + fallbackFilename + "; filename*=UTF-8''"
                    + URLEncoder.encode(filename, StandardCharsets.UTF_8).replace("+", "%20");
        }
        return new ExcelFile(response.body(), disposition);
    }

    private Map<String, Object> sendJson(HttpRequest request) throws Exception
    {
        HttpResponse<String> response = httpClient.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        Map<String, Object> body = parseJson(response.body());
        if (response.statusCode() >= 400 || integer(body.get("code"), -1) != 0)
            throw new IllegalStateException(errorMessage(body, response.statusCode(), SERVICE_NAME));
        return body;
    }

    public record ExcelFile(byte[] content, String contentDisposition) {}
}
