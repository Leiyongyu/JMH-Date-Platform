package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.finance.PythonHttpSupport;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

/** ERP 到 Python eBay补货2.0服务的只读内部客户端。 */
@Service
public class EbayReplenishmentV2PythonClient extends PythonHttpSupport
{
    private static final String PREFIX = "/ebay-replenishment-v2";
    private static final String SERVICE_NAME = "Python eBay补货2.0服务";

    public EbayReplenishmentV2PythonClient(
            PerformancePythonProperties properties,
            ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    public Map<String, Object> list(Map<String, ?> params, String requestId)
    {
        return get(PREFIX + "/list", params, requestId);
    }

    private Map<String, Object> get(
            String path,
            Map<String, ?> params,
            String requestId)
    {
        try
        {
            HttpRequest request = baseRequest(
                    path + queryString(params), requestId)
                    .GET()
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Map<String, Object> send(HttpRequest request) throws Exception
    {
        HttpResponse<String> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        Map<String, Object> body = parseJson(response.body());
        if (response.statusCode() >= 400
                || integer(body.get("code"), -1) != 0)
        {
            throw new IllegalStateException(errorMessage(
                    body, response.statusCode(), SERVICE_NAME));
        }
        return body;
    }
}
