package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.finance.PythonHttpSupport;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** ERP到Python eBay SKU分析服务的内部客户端。 */
@Service
public class EbaySkuAnalysisPythonClient extends PythonHttpSupport
{
    private static final String PREFIX = "/ebay-sku-analysis";

    public EbaySkuAnalysisPythonClient(PerformancePythonProperties properties, ObjectMapper objectMapper)
    {
        super(properties, objectMapper);
    }

    public Map<String, Object> dates(String requestId)
    {
        return get(PREFIX + "/dates", Map.of(), requestId);
    }

    public Map<String, Object> summary(Map<String, ?> params, String requestId)
    {
        return get(PREFIX + "/summary", params, requestId);
    }

    public Map<String, Object> importOrders(MultipartFile file, String operator, String requestId)
    {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("请选择有效Excel文件");
        try
        {
            String boundary = "----JmhEbaySku" + UUID.randomUUID().toString().replace("-", "");
            HttpRequest request = baseRequest(PREFIX + "/imports" + queryString(Map.of("operator", operator)), requestId)
                    .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                    .POST(multipartBodyPublisher(boundary, "file", new MultipartFile[] { file })).build();
            return send(request);
        }
        catch (Exception e) { throw asRuntime(e); }
    }

    private Map<String, Object> get(String path, Map<String, ?> params, String requestId)
    {
        try { return send(baseRequest(path + queryString(params), requestId).GET().build()); }
        catch (Exception e) { throw asRuntime(e); }
    }

    private Map<String, Object> send(HttpRequest request) throws Exception
    {
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        Map<String, Object> body = objectMapper.readValue(response.body(), new TypeReference<LinkedHashMap<String, Object>>() {});
        if (response.statusCode() >= 400 || !Integer.valueOf(0).equals(body.get("code")))
            throw new IllegalStateException(String.valueOf(body.getOrDefault("message", "Python eBay SKU分析服务调用失败")));
        return body;
    }
}
