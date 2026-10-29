package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.finance.PythonHttpSupport;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

/** ERP 到 Python eBay补货2.0服务的内部客户端。 */
@Service
public class EbayReplenishmentV2PythonClient extends PythonHttpSupport
{
    @org.springframework.beans.factory.annotation.Autowired
    private com.ruoyi.system.service.operation.scope.BusinessDataScopeService dataScope;

    /** Used by local Java row writes as well as proxied writes. */
    public void requireRow(String site, String sku, String requestId)
    {
        var scope = dataScope.resolve(com.ruoyi.system.service.operation.scope.BusinessDataScopeService.EBAY);
        if (scope.isAll()) return;
        if (site == null || site.isBlank() || sku == null || sku.isBlank())
            throw new org.springframework.security.access.AccessDeniedException("站点和SKU不能为空");
        Map<String, Object> result = list(Map.of("site", site, "sku", sku,
                "exact_sku", true, "page_size", 1), requestId);
        if (!(result.get("data") instanceof Map<?, ?> data)
                || !(data.get("items") instanceof java.util.List<?> items) || items.isEmpty())
            throw new org.springframework.security.access.AccessDeniedException("无权查看或操作该补货记录");
    }

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

    public Map<String, Object> hierarchy(Map<String, ?> params, String requestId)
    {
        return get(PREFIX + "/hierarchy", params, requestId);
    }

    public Map<String, Object> mixedSales(Map<String, ?> params, boolean details, String requestId)
    {
        return get(PREFIX + "/mixed-sales" + (details ? "/details" : ""), params, requestId);
    }

    public Map<String, Object> mixedSalesPrices(Map<String, ?> params, String requestId)
    {
        return get(PREFIX + "/mixed-sales/prices", params, requestId);
    }

    public Map<String, Object> exportData(Map<String, ?> params, String requestId)
    {
        return get(PREFIX + "/export-data", params, requestId);
    }

    public Map<String, Object> formula(String requestId)
    {
        return get(PREFIX + "/formula", Map.of(), requestId);
    }

    public Map<String, Object> saveReviewNote(Map<String, ?> body, String requestId)
    {
        requireRow((String) body.get("site"), (String) body.get("sku"), requestId);
        return post(PREFIX + "/review/note", body, requestId);
    }

    public Map<String, Object> confirmReview(Map<String, ?> body, String requestId)
    {
        requireRow((String) body.get("site"), (String) body.get("sku"), requestId);
        return post(PREFIX + "/review/confirm", body, requestId);
    }

    public Map<String, Object> saveSalesType(Map<String, ?> body, String requestId)
    {
        requireRow((String) body.get("site"), (String) body.get("sku"), requestId);
        return post(PREFIX + "/sales-type", body, requestId);
    }

    public Map<String, Object> saveFormula(
            Map<String, ?> body, String requestId)
    {
        return post(PREFIX + "/formula", body, requestId);
    }

    public Map<String, Object> levelRules(String requestId)
    {
        return get(PREFIX + "/level-rule", Map.of(), requestId);
    }

    public Map<String, Object> saveLevelRules(Map<String, ?> body, String requestId)
    {
        return post(PREFIX + "/level-rule", body, requestId);
    }

    public Map<String, Object> validateLevelRules(Map<String, ?> body, String requestId)
    {
        return post(PREFIX + "/level-rule/validate", body, requestId);
    }

    public Map<String, Object> forecastRules(String requestId)
    {
        return get(PREFIX + "/forecast-rule", Map.of(), requestId);
    }

    public Map<String, Object> saveForecastRules(Map<String, ?> body, String requestId)
    {
        return post(PREFIX + "/forecast-rule", body, requestId);
    }

    public Map<String, Object> validateForecastRules(Map<String, ?> body, String requestId)
    {
        return post(PREFIX + "/forecast-rule/validate", body, requestId);
    }

    public Map<String, Object> previewForecastRules(Map<String, ?> body, String requestId)
    {
        return post(PREFIX + "/forecast-rule/preview", body, requestId);
    }

    public Map<String, Object> forecastRuleSku(Map<String, ?> params, String requestId)
    {
        requireRow((String) params.get("site"), (String) params.get("sku"), requestId);
        return get(PREFIX + "/forecast-rule/sku", params, requestId);
    }

    private Map<String, Object> post(
            String path, Map<String, ?> body, String requestId)
    {
        try
        {
            String json = objectMapper.writeValueAsString(body);
            HttpRequest request = baseRequest(path, requestId)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            json, StandardCharsets.UTF_8))
                    .build();
            return send(request);
        }
        catch (Exception e)
        {
            throw asRuntime(e);
        }
    }

    private Map<String, Object> get(
            String path,
            Map<String, ?> params,
            String requestId)
    {
        try
        {
            Map<String, Object> scopedParams = new java.util.LinkedHashMap<>(params);
            if (java.util.Set.of(PREFIX + "/list", PREFIX + "/hierarchy", PREFIX + "/export-data").contains(path))
            {
                var scope = dataScope.resolve(com.ruoyi.system.service.operation.scope.BusinessDataScopeService.EBAY);
                // Always replace client-supplied scope. JSON null explicitly means all.
                scopedParams.put("allowed_principals", objectMapper.writeValueAsString(scope.isAll() ? null : scope.getOwners()));
            }
            HttpRequest request = baseRequest(
                    path + queryString(scopedParams), requestId)
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
