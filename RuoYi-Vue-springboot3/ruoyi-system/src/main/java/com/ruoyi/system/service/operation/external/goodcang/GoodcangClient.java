package com.ruoyi.system.service.operation.external.goodcang;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * 谷仓(GoodCang) WMS API HTTP 客户端 —— 使用 Basic Auth 头认证。
 * 从旧项目 Operational-Project 迁移，统一使用 java.net.http.HttpClient。
 *
 * @author JMH
 */
@Service
public class GoodcangClient
{
    private final GoodcangProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public GoodcangClient(GoodcangProperties properties, ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.getConnectTimeout()))
                .build();
    }

    /** 获取仓库列表 */
    public Map<String, Object> getWarehouses() throws Exception
    {
        return post("/base_data/get_warehouse", new LinkedHashMap<>());
    }

    /** 获取入库单列表（分页） */
    public Map<String, Object> getGrnList(String createDateFrom, String createDateTo,
                                           int page, int pageSize) throws Exception
    {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("create_date_from", createDateFrom);
        body.put("create_date_to", createDateTo);
        body.put("page", page);
        body.put("pageSize", pageSize);
        return post("/inbound_order/get_grn_list", body);
    }

    /** 获取入库单详情 */
    public Map<String, Object> getGrnDetail(String receivingCode) throws Exception
    {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("receiving_code", receivingCode);
        return post("/inbound_order/get_grn_detail", body);
    }

    /** 获取商品列表（分页） */
    public Map<String, Object> getProductList(int page, int pageSize) throws Exception
    {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("page", page);
        body.put("pageSize", pageSize);
        return post("/product/get_product_sku_list", body);
    }

    // ========== 内部方法 ==========

    private Map<String, Object> post(String path, Map<String, Object> body) throws Exception
    {
        String url = trimRight(properties.getEndpoint(), "/") + "/" + trimLeft(path, "/");
        String json = objectMapper.writeValueAsString(body);

        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofMillis(properties.getReadTimeout()))
                .header("Content-Type", "application/json;charset=UTF-8")
                .header("app-token", properties.getAppToken())
                .header("app-key", properties.getAppKey())
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = httpClient.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        if (response.statusCode() < 200 || response.statusCode() >= 300)
        {
            throw new IllegalStateException(
                    "Goodcang HTTP " + response.statusCode() + ": " + response.body());
        }
        return objectMapper.readValue(response.body(),
                new TypeReference<Map<String, Object>>() {});
    }

    private String trimLeft(String value, String token)
    {
        String result = (value != null) ? value.trim() : "";
        while (result.startsWith(token)) result = result.substring(token.length());
        return result;
    }

    private String trimRight(String value, String token)
    {
        String result = (value != null) ? value.trim() : "";
        while (result.endsWith(token)) result = result.substring(0, result.length() - token.length());
        return result;
    }
}
