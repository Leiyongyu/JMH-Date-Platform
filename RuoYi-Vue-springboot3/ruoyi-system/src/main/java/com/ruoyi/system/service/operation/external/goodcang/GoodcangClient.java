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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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
    private static final Logger LOG = LoggerFactory.getLogger(GoodcangClient.class);

    private final GoodcangProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;
    private final Object requestGate = new Object();
    private long nextRequestAt;

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

    /** 获取入库单列表（全量，不传时间参数） */
    public Map<String, Object> getGrnListAll(int page, int pageSize) throws Exception
    {
        Map<String, Object> body = new LinkedHashMap<>();
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

    /** 获取库龄列表（文档规定每页最大200条） */
    public Map<String, Object> getInventoryAgeList(int page, int pageSize)
            throws Exception
    {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("page", page);
        body.put("page_size", pageSize);
        return post("/inventory/inventory_age_list", body);
    }

    // ========== 内部方法 ==========

    private Map<String, Object> post(String path, Map<String, Object> body) throws Exception
    {
        String url = trimRight(properties.getEndpoint(), "/") + "/" + trimLeft(path, "/");
        String json = objectMapper.writeValueAsString(body);

        int maxRetries = Math.max(0, properties.getMaxRateLimitRetries());
        for (int retry = 0; retry <= maxRetries; retry++)
        {
            waitForRequestSlot();
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofMillis(properties.getReadTimeout()))
                    .header("Content-Type", "application/json;charset=UTF-8")
                    .header("app-token", properties.getAppToken())
                    .header("app-key", properties.getAppKey())
                    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = httpClient.send(request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() >= 200 && response.statusCode() < 300)
                return objectMapper.readValue(response.body(),
                        new TypeReference<Map<String, Object>>() {});

            if (response.statusCode() != 429 || retry >= maxRetries)
            {
                String suffix = response.statusCode() == 429
                        ? "；已自动重试" + retry + "次"
                        : "";
                throw new IllegalStateException(
                        "Goodcang HTTP " + response.statusCode() + ": "
                                + response.body() + suffix);
            }

            long delayMs = retryDelayMs(response, retry);
            LOG.warn("Goodcang HTTP 429，{}ms后进行第{}次重试: path={}",
                    delayMs, retry + 1, path);
            sleep(delayMs);
        }
        throw new IllegalStateException("Goodcang请求重试流程异常终止: " + path);
    }

    private void waitForRequestSlot() throws InterruptedException
    {
        long waitMs;
        long intervalMs = Math.max(0L, properties.getMinRequestIntervalMs());
        synchronized (requestGate)
        {
            long now = System.currentTimeMillis();
            waitMs = Math.max(0L, nextRequestAt - now);
            nextRequestAt = Math.max(now, nextRequestAt) + intervalMs;
        }
        sleep(waitMs);
    }

    private long retryDelayMs(HttpResponse<String> response, int retry)
    {
        String retryAfter = response.headers().firstValue("Retry-After").orElse(null);
        if (retryAfter != null)
        {
            try
            {
                return Math.max(0L, Long.parseLong(retryAfter.trim()) * 1000L);
            }
            catch (NumberFormatException ignored)
            {
                // 非秒数格式时使用本地指数退避。
            }
        }
        long initial = Math.max(1L, properties.getRateLimitInitialBackoffMs());
        long maximum = Math.max(initial, properties.getRateLimitMaxBackoffMs());
        long multiplier = 1L << Math.min(retry, 20);
        if (initial > Long.MAX_VALUE / multiplier) return maximum;
        return Math.min(maximum, initial * multiplier);
    }

    private void sleep(long delayMs) throws InterruptedException
    {
        if (delayMs <= 0L) return;
        try
        {
            Thread.sleep(delayMs);
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw e;
        }
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
