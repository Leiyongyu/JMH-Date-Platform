package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.python.PythonHttpSupport;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * ERP 到 Python「eBay 周五数据」服务的内部客户端（/api/v1/finance/ebay-friday-report）。
 * 与绩效、AMZ月度利润表共用 PerformancePythonProperties（base-url 已带 /api/v1/finance），
 * 内部 Token 与请求 ID 由 PythonHttpSupport 统一带上。
 */
@Service
public class EbayFridayReportPythonClient extends PythonHttpSupport
{
    static final String PREFIX = "/ebay-friday-report";
    private static final String SERVICE_NAME = "Python eBay周五数据服务";
    private static final String EXCEL_CONTENT_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    public EbayFridayReportPythonClient(PerformancePythonProperties properties, ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    public Map<String, Object> overview(Map<String, String> query, String requestId)
    {
        return send(baseRequest(PREFIX + "/overview" + queryString(query), requestId).GET().build());
    }

    public Map<String, Object> listings(Map<String, String> query, String requestId)
    {
        return send(baseRequest(PREFIX + "/listings" + queryString(query), requestId).GET().build());
    }

    public Map<String, Object> stocks(Map<String, String> query, String requestId)
    {
        return send(baseRequest(PREFIX + "/stocks" + queryString(query), requestId).GET().build());
    }

    public Map<String, Object> generate(Map<String, ?> body, String requestId)
    {
        return send(json(baseRequest(PREFIX + "/generate", requestId), "POST", body));
    }

    public Map<String, Object> saveStore(Map<String, ?> body, String requestId)
    {
        return send(json(baseRequest(PREFIX + "/stores", requestId), "PUT", body));
    }

    public Map<String, Object> deleteStore(String storeKey, String requestId)
    {
        String key = URLEncoder.encode(storeKey, StandardCharsets.UTF_8).replace("+", "%20");
        return send(baseRequest(PREFIX + "/stores/" + key, requestId).DELETE().build());
    }

    public byte[] export(Map<String, String> query, String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(PREFIX + "/exports" + queryString(query), requestId)
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

    private HttpRequest json(HttpRequest.Builder builder, String method, Map<String, ?> body)
    {
        try
        {
            String text = objectMapper.writeValueAsString(body == null ? Map.of() : body);
            return builder.header("Content-Type", "application/json;charset=utf-8")
                    .method(method, HttpRequest.BodyPublishers.ofString(text, StandardCharsets.UTF_8))
                    .build();
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
