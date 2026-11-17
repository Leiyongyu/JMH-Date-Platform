package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.python.PythonHttpSupport;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

/**
 * ERP 到 Python「项目利润总表」服务的内部客户端（/api/v1/finance/project-profit）。
 * 与 AMZ 月度利润表共用 PerformancePythonProperties（base-url 已带 /api/v1/finance），
 * 内部 Token 与请求 ID 由 PythonHttpSupport 统一带上。
 */
@Service
public class ProjectProfitPythonClient extends PythonHttpSupport
{
    static final String PREFIX = "/project-profit";
    static final long MAX_UPLOAD_BYTES = 50L * 1024 * 1024;
    private static final String SERVICE_NAME = "Python 项目利润总表服务";
    private static final String EXCEL_CONTENT_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    public ProjectProfitPythonClient(PerformancePythonProperties properties, ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    public Map<String, Object> months(String requestId)
    {
        return send(baseRequest(PREFIX + "/months", requestId).GET().build());
    }

    public Map<String, Object> report(String statMonth, String requestId)
    {
        return send(baseRequest(PREFIX + "/report" + queryString(Map.of("stat_month", statMonth)), requestId)
                .GET().build());
    }

    public Map<String, Object> saveItems(Map<String, ?> body, String requestId)
    {
        try
        {
            String text = objectMapper.writeValueAsString(body == null ? Map.of() : body);
            return send(baseRequest(PREFIX + "/items", requestId)
                    .header("Content-Type", "application/json;charset=utf-8")
                    .PUT(HttpRequest.BodyPublishers.ofString(text, StandardCharsets.UTF_8))
                    .build());
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public Map<String, Object> importEbay(MultipartFile file, String statMonth, String operator, String requestId)
    {
        return upload("/ebay/import", "请选择 eBay 利润明细表", file, statMonth, operator, requestId);
    }

    /** 领星「利润报表-MSKU」手动导出（人民币），项目利润总表 AMZ 各列的数据来源。 */
    public Map<String, Object> importAmz(MultipartFile file, String statMonth, String operator, String requestId)
    {
        return upload("/amz/import", "请选择领星利润报表-MSKU 文件", file, statMonth, operator, requestId);
    }

    private Map<String, Object> upload(String path, String emptyMessage, MultipartFile file, String statMonth,
            String operator, String requestId)
    {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException(emptyMessage);
        if (file.getSize() > MAX_UPLOAD_BYTES) throw new IllegalArgumentException("文件不能超过50MB");
        try
        {
            String boundary = "----ProjectProfitUpload" + UUID.randomUUID().toString().replace("-", "");
            HttpRequest request = baseRequest(PREFIX + path + queryString(Map.of(
                            "stat_month", statMonth, "operator", operator == null ? "" : operator)), requestId)
                    .timeout(java.time.Duration.ofSeconds(300))
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(multipartBodyPublisher(boundary, "file", new MultipartFile[] { file }))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    public byte[] export(String statMonth, String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(
                    PREFIX + "/exports" + queryString(Map.of("stat_month", statMonth)), requestId)
                    .setHeader("Accept", EXCEL_CONTENT_TYPE)
                    .GET().build();
            HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() >= 400)
            {
                throw new IllegalStateException(errorMessage(
                        parseJson(new String(response.body(), StandardCharsets.UTF_8)),
                        response.statusCode(), SERVICE_NAME));
            }
            return response.body();
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Map<String, Object> send(HttpRequest request)
    {
        try
        {
            HttpResponse<String> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            Map<String, Object> body = parseJson(response.body());
            if (response.statusCode() >= 400 || integer(body.get("code"), -1) != 0)
                throw new IllegalStateException(errorMessage(body, response.statusCode(), SERVICE_NAME));
            return body;
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }
}
