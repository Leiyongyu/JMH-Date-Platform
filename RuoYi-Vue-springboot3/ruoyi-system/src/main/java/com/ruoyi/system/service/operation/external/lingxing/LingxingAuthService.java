package com.ruoyi.system.service.operation.external.lingxing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class LingxingAuthService
{
    private final LingxingProperties properties;
    private final LingxingOpenApiClient client;
    private final ObjectMapper objectMapper;
    private final Object tokenLock = new Object();
    private volatile CachedToken cachedToken;

    public LingxingAuthService(LingxingProperties properties, LingxingOpenApiClient client, ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.client = client;
        this.objectMapper = objectMapper;
    }

    public Map<String, Object> getAccessTokenResponse() throws Exception
    {
        Map<String, String> query = new LinkedHashMap<>();
        query.put("appId", properties.getAppId());
        query.put("appSecret", properties.getAppSecret());
        return client.postForm("api/auth-server/oauth/access-token", query);
    }

    public String getAccessToken() throws Exception
    {
        CachedToken token = cachedToken;
        if (token != null && token.isValid(properties.getTokenRefreshSkewSeconds()))
        {
            return token.accessToken;
        }

        synchronized (tokenLock)
        {
            token = cachedToken;
            if (token != null && token.isValid(properties.getTokenRefreshSkewSeconds()))
            {
                return token.accessToken;
            }

            CachedToken updated = refreshOrFetchToken(token);
            cachedToken = updated;
            return updated.accessToken;
        }
    }

    private CachedToken refreshOrFetchToken(CachedToken existing) throws Exception
    {
        if (existing != null && StringUtils.hasText(existing.refreshToken))
        {
            CachedToken refreshed = tryRefresh(existing.refreshToken);
            if (refreshed != null && refreshed.isValid(0))
            {
                return refreshed;
            }
        }
        return fetchByAppSecret();
    }

    private CachedToken fetchByAppSecret() throws Exception
    {
        Map<String, Object> response = getAccessTokenResponse();
        if (!isSuccessCode(response.get("code")))
        {
            throw new IllegalStateException("Lingxing access_token failed: code=" + response.get("code") + ", msg=" + response.get("msg"));
        }
        CachedToken token = extractToken(response.get("data"));
        if (token == null || !StringUtils.hasText(token.accessToken))
        {
            throw new IllegalStateException("Lingxing access_token response does not contain token");
        }
        return token;
    }

    private CachedToken tryRefresh(String refreshToken)
    {
        try
        {
            Map<String, String> query = new LinkedHashMap<>();
            query.put("appId", properties.getAppId());
            query.put("refreshToken", refreshToken);
            Map<String, Object> response = client.postForm("api/auth-server/oauth/refresh", query);
            if (!isSuccessCode(response.get("code")))
            {
                return null;
            }
            return extractToken(response.get("data"));
        }
        catch (Exception ignored)
        {
            return null;
        }
    }

    private CachedToken extractToken(Object data)
    {
        if (data == null)
        {
            return null;
        }
        if (data instanceof String)
        {
            CachedToken token = new CachedToken();
            token.accessToken = (String) data;
            token.expiresAtMillis = System.currentTimeMillis();
            return token;
        }
        Map<String, Object> map = objectMapper.convertValue(data, new TypeReference<Map<String, Object>>() {});
        String accessToken = firstNonBlank(map.get("access_token"), map.get("accessToken"), map.get("token"));
        String refreshToken = firstNonBlank(map.get("refresh_token"), map.get("refreshToken"));
        long expiresInSeconds = parseLong(firstNonBlank(map.get("expires_in"), map.get("expiresIn")), 0L);

        CachedToken token = new CachedToken();
        token.accessToken = accessToken;
        token.refreshToken = refreshToken;
        token.expiresAtMillis = expiresInSeconds > 0 ? System.currentTimeMillis() + expiresInSeconds * 1000L : System.currentTimeMillis();
        return token;
    }

    private String firstNonBlank(Object... values)
    {
        for (Object value : values)
        {
            if (value != null && StringUtils.hasText(String.valueOf(value)))
            {
                return String.valueOf(value);
            }
        }
        return null;
    }

    private boolean isSuccessCode(Object code)
    {
        if (code == null)
        {
            return false;
        }
        String text = String.valueOf(code);
        return "0".equals(text) || "200".equals(text) || "OK".equalsIgnoreCase(text) || "SUCCESS".equalsIgnoreCase(text);
    }

    private long parseLong(String value, long defaultValue)
    {
        if (!StringUtils.hasText(value))
        {
            return defaultValue;
        }
        try
        {
            return Long.parseLong(value);
        }
        catch (Exception e)
        {
            return defaultValue;
        }
    }

    private static final class CachedToken
    {
        private String accessToken;
        private String refreshToken;
        private long expiresAtMillis;

        private boolean isValid(int skewSeconds)
        {
            return StringUtils.hasText(accessToken) && System.currentTimeMillis() + Math.max(0, skewSeconds) * 1000L < expiresAtMillis;
        }
    }
}
