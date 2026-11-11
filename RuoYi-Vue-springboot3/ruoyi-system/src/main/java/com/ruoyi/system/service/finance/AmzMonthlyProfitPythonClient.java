package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.python.PythonHttpSupport;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * ERP 到 Python「AMZ月度利润表」服务的内部客户端（/api/v1/finance/amz-monthly-profit）。
 * 与绩效、AMZ利润报表共用 PerformancePythonProperties（base-url 已带 /api/v1/finance），
 * 内部 Token 与请求 ID 由 PythonHttpSupport 统一带上。
 */
@Service
public class AmzMonthlyProfitPythonClient extends PythonHttpSupport
{
    static final String PREFIX = "/amz-monthly-profit";
    private static final String SERVICE_NAME = "Python AMZ月度利润表服务";
    private static final String EXCEL_CONTENT_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    public AmzMonthlyProfitPythonClient(PerformancePythonProperties properties, ObjectMapper objectMapper)
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

    public Map<String, Object> adjustments(String statMonth, String requestId)
    {
        return send(baseRequest(PREFIX + "/adjustments" + queryString(Map.of("stat_month", statMonth)), requestId)
                .GET().build());
    }

    public Map<String, Object> createAdjustment(Map<String, ?> body, String requestId)
    {
        return send(json(baseRequest(PREFIX + "/adjustments", requestId), "POST", body));
    }

    public Map<String, Object> updateAdjustment(long id, Map<String, ?> body, String requestId)
    {
        return send(json(baseRequest(PREFIX + "/adjustments/" + id, requestId), "PUT", body));
    }

    public Map<String, Object> deleteAdjustment(long id, String requestId)
    {
        return send(baseRequest(PREFIX + "/adjustments/" + id, requestId).DELETE().build());
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
