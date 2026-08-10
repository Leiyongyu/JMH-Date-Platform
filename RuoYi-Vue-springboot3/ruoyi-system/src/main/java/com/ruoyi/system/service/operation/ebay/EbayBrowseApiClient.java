package com.ruoyi.system.service.operation.ebay;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.StringJoiner;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.exception.ServiceException;
import org.springframework.stereotype.Component;

/**
 * eBay 官方 Buy Browse API 客户端。
 */
@Component
public class EbayBrowseApiClient
{
    private static final Map<String, String> MARKETPLACES = Map.of(
            "de", "EBAY_DE",
            "uk", "EBAY_GB",
            "us", "EBAY_US");

    private final EbayProperties properties;
    private final EbayOAuthTokenProvider tokenProvider;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public EbayBrowseApiClient(EbayProperties properties,
            EbayOAuthTokenProvider tokenProvider, ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.tokenProvider = tokenProvider;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(properties.getConnectTimeout())
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public JsonNode searchItems(String keyword, String site, String sort, int limit)
    {
        if (!"price".equals(sort) && !"-price".equals(sort))
        {
            throw new ServiceException("eBay价格排序仅支持 price 或 -price");
        }
        LinkedHashMap<String, String> query = new LinkedHashMap<>();
        query.put("q", keyword);
        query.put("limit", String.valueOf(Math.min(Math.max(limit, 1), 200)));
        query.put("offset", "0");
        query.put("sort", sort);
        query.put("filter", "conditions:{NEW}");
        query.put("fieldgroups", "MATCHING_ITEMS");
        return get("/buy/browse/v1/item_summary/search", query, site);
    }

    public JsonNode getItem(String itemId, String site)
    {
        if (itemId == null || itemId.isBlank())
        {
            throw new ServiceException("eBay itemId 不能为空");
        }
        return get("/buy/browse/v1/item/" + encode(itemId), Map.of(), site);
    }

    private JsonNode get(String path, Map<String, String> query, String site)
    {
        String marketplace = MARKETPLACES.get(normalizeSite(site));
        if (marketplace == null)
        {
            throw new ServiceException("不支持的 eBay 站点: " + site);
        }
        int maxAttempts = Math.max(1, properties.getDetailMaxRetries());
        String token = tokenProvider.getAccessToken();
        boolean tokenRefreshed = false;
        for (int attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                HttpRequest.Builder builder = HttpRequest.newBuilder()
                        .uri(buildUri(path, query))
                        .timeout(properties.getRequestTimeout())
                        .header("Authorization", "Bearer " + token)
                        .header("Accept", "application/json")
                        .header("X-EBAY-C-MARKETPLACE-ID", marketplace)
                        .GET();
                if (properties.getEndUserContext() != null
                        && !properties.getEndUserContext().trim().isEmpty())
                {
                    builder.header("X-EBAY-C-ENDUSERCTX", properties.getEndUserContext().trim());
                }
                HttpResponse<String> response = httpClient.send(builder.build(),
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                int status = response.statusCode();
                if (status >= 200 && status < 300)
                {
                    return response.body() == null || response.body().isBlank()
                            ? objectMapper.createObjectNode()
                            : objectMapper.readTree(response.body());
                }
                if (status == 401 && !tokenRefreshed)
                {
                    tokenProvider.invalidate(token);
                    token = tokenProvider.getAccessToken();
                    tokenRefreshed = true;
                    attempt--;
                    continue;
                }
                if ((status == 429 || status >= 500) && attempt < maxAttempts)
                {
                    backoff(attempt);
                    continue;
                }
                throw new ServiceException("eBay API 返回错误[HTTP " + status + "]: "
                        + safeBody(response.body()));
            }
            catch (ServiceException e)
            {
                throw e;
            }
            catch (InterruptedException e)
            {
                Thread.currentThread().interrupt();
                throw new ServiceException("eBay API 请求已中断");
            }
            catch (Exception e)
            {
                if (attempt < maxAttempts)
                {
                    backoff(attempt);
                    continue;
                }
                throw new ServiceException("eBay API 请求失败: " + e.getMessage());
            }
        }
        throw new ServiceException("eBay API 请求失败");
    }

    private URI buildUri(String path, Map<String, String> query)
    {
        String base = properties.getBaseUrl() == null ? "" : properties.getBaseUrl().trim();
        if (base.endsWith("/"))
        {
            base = base.substring(0, base.length() - 1);
        }
        if (query.isEmpty())
        {
            return URI.create(base + path);
        }
        StringJoiner values = new StringJoiner("&");
        query.forEach((key, value) -> values.add(encode(key) + "=" + encode(value)));
        return URI.create(base + path + "?" + values);
    }

    private static String normalizeSite(String site)
    {
        return site == null ? "" : site.trim().toLowerCase();
    }

    private static String encode(String value)
    {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8)
                .replace("+", "%20");
    }

    private static String safeBody(String body)
    {
        if (body == null)
        {
            return "";
        }
        String compact = body.replaceAll("[\\r\\n]+", " ");
        return compact.length() <= 500 ? compact : compact.substring(0, 500);
    }

    private static void backoff(int attempt)
    {
        try
        {
            Thread.sleep(Math.min(2000L, 250L * (1L << Math.min(attempt - 1, 3))));
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw new ServiceException("eBay API 重试等待已中断");
        }
    }
}
