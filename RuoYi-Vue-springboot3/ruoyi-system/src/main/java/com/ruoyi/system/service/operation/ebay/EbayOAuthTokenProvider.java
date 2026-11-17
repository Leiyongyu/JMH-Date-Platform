package com.ruoyi.system.service.operation.ebay;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.exception.ServiceException;
import org.springframework.stereotype.Component;

/**
 * eBay Application Token 缓存。Token 在过期前 60 秒刷新，刷新过程串行化。
 */
@Component
public class EbayOAuthTokenProvider
{
    private static final String SCOPE = "https://api.ebay.com/oauth/api_scope";

    private final EbayProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;
    private final Object tokenLock = new Object();
    private volatile CachedToken cachedToken;

    public EbayOAuthTokenProvider(EbayProperties properties, ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(properties.getConnectTimeout())
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public String getAccessToken()
    {
        CachedToken current = cachedToken;
        if (current != null && Instant.now().isBefore(current.expiresAt))
        {
            return current.value;
        }
        synchronized (tokenLock)
        {
            current = cachedToken;
            if (current != null && Instant.now().isBefore(current.expiresAt))
            {
                return current.value;
            }
            cachedToken = requestToken();
            return cachedToken.value;
        }
    }

    public void invalidate(String tokenValue)
    {
        synchronized (tokenLock)
        {
            if (cachedToken != null && cachedToken.value.equals(tokenValue))
            {
                cachedToken = null;
            }
        }
    }

    public boolean isConfigured()
    {
        return hasText(properties.getClientId()) && hasText(properties.getClientSecret());
    }

    private CachedToken requestToken()
    {
        if (!isConfigured())
        {
            throw new ServiceException("eBay配置不完整，请设置 EBAY_CLIENT_ID、EBAY_CLIENT_SECRET");
        }
        try
        {
            String credentials = properties.getClientId() + ":" + properties.getClientSecret();
            String authorization = "Basic " + Base64.getEncoder()
                    .encodeToString(credentials.getBytes(StandardCharsets.UTF_8));
            String body = "grant_type=client_credentials&scope="
                    + URLEncoder.encode(SCOPE, StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl() + "/identity/v1/oauth2/token"))
                    .timeout(properties.getRequestTimeout())
                    .header("Authorization", authorization)
                    .header("Content-Type", "application/x-www-form-urlencoded")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = httpClient.send(request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() < 200 || response.statusCode() >= 300)
            {
                throw new ServiceException("eBay OAuth 请求失败[HTTP " + response.statusCode()
                        + "]: " + safeBody(response.body()));
            }
            JsonNode payload = objectMapper.readTree(response.body());
            String accessToken = payload.path("access_token").asText("");
            if (!hasText(accessToken))
            {
                throw new ServiceException("eBay OAuth 响应缺少 access_token");
            }
            long expiresIn = payload.path("expires_in").asLong(7200L);
            long validSeconds = Math.max(expiresIn - 60L, 60L);
            return new CachedToken(accessToken, Instant.now().plusSeconds(validSeconds));
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            throw new ServiceException("eBay OAuth 请求已中断");
        }
        catch (Exception e)
        {
            throw new ServiceException("eBay OAuth 请求失败: " + e.getMessage());
        }
    }

    private String baseUrl()
    {
        String value = properties.getBaseUrl() == null ? "" : properties.getBaseUrl().trim();
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    private static boolean hasText(String value)
    {
        return value != null && !value.trim().isEmpty();
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

    private static final class CachedToken
    {
        private final String value;
        private final Instant expiresAt;

        private CachedToken(String value, Instant expiresAt)
        {
            this.value = value;
            this.expiresAt = expiresAt;
        }
    }
}
