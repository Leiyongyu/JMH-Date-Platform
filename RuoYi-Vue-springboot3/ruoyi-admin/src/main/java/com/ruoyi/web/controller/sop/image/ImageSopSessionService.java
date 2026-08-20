package com.ruoyi.web.controller.sop.image;

import com.ruoyi.common.core.redis.RedisCache;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 为Python脚本工作台签发带ERP用户及权限作用域的临时会话。
 * 会话保存在Redis，支持Java重启及多实例；固定最长8小时，空闲1小时失效。
 */
@Service
public class ImageSopSessionService
{
    public static final String IMAGE_SOP_PERMISSION = "sop:imageSop:use";
    private static final String CACHE_PREFIX = "sop:python-tools:session:";
    private static final Duration ABSOLUTE_TTL = Duration.ofHours(8);
    private static final Duration IDLE_TTL = Duration.ofHours(1);
    private static final int TOKEN_BYTES = 32;

    private final SecureRandom secureRandom = new SecureRandom();
    private final RedisCache redisCache;

    public ImageSopSessionService(RedisCache redisCache)
    {
        this.redisCache = redisCache;
    }

    public SessionTicket issue(Long userId, String username,
            Collection<String> permissions)
    {
        byte[] random = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(random);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        Instant now = Instant.now();
        Instant expiresAt = now.plus(ABSOLUTE_TTL);
        Set<String> granted = new LinkedHashSet<>();
        if (permissions != null)
        {
            for (String permission : permissions)
            {
                if (StringUtils.hasText(permission))
                    granted.add(permission.trim());
            }
        }

        Map<String, Object> state = new LinkedHashMap<>();
        state.put("userId", userId);
        state.put("username", username == null ? "" : username);
        state.put("permissions", new ArrayList<>(granted));
        state.put("issuedAt", now.toEpochMilli());
        state.put("expiresAt", expiresAt.toEpochMilli());
        redisCache.setCacheObject(cacheKey(token), state,
                (int) IDLE_TTL.toSeconds(), TimeUnit.SECONDS);
        return new SessionTicket(token, ABSOLUTE_TTL.toSeconds(),
                IDLE_TTL.toSeconds(), expiresAt);
    }

    /** 兼容图片SOP旧入口，但会话只能访问图片SOP。 */
    public SessionTicket issue(Long userId, String username)
    {
        return issue(userId, username, Set.of(IMAGE_SOP_PERMISSION));
    }

    public SessionContext validateAndTouch(String token, String requiredPermission)
    {
        if (!StringUtils.hasText(token))
            return null;
        Map<String, Object> state = redisCache.getCacheObject(cacheKey(token));
        if (state == null || state.isEmpty())
            return null;

        Instant now = Instant.now();
        long expiresAtMillis = longValue(state.get("expiresAt"));
        Instant expiresAt = Instant.ofEpochMilli(expiresAtMillis);
        if (!expiresAt.isAfter(now))
        {
            redisCache.deleteObject(cacheKey(token));
            return null;
        }

        Set<String> permissions = stringSet(state.get("permissions"));
        if (StringUtils.hasText(requiredPermission)
                && !permissions.contains(requiredPermission.trim()))
            return null;

        long remainingSeconds = Math.max(1,
                Duration.between(now, expiresAt).toSeconds());
        redisCache.expire(cacheKey(token),
                Math.min(IDLE_TTL.toSeconds(), remainingSeconds),
                TimeUnit.SECONDS);
        return new SessionContext(
                longValue(state.get("userId")),
                String.valueOf(state.getOrDefault("username", "")),
                permissions,
                expiresAt);
    }

    public boolean validateAndTouch(String token)
    {
        return validateAndTouch(token, null) != null;
    }

    private String cacheKey(String token)
    {
        return CACHE_PREFIX + token.trim();
    }

    private long longValue(Object value)
    {
        if (value instanceof Number number)
            return number.longValue();
        try
        {
            return Long.parseLong(String.valueOf(value));
        }
        catch (Exception ignored)
        {
            return 0L;
        }
    }

    private Set<String> stringSet(Object value)
    {
        Set<String> result = new LinkedHashSet<>();
        if (value instanceof Collection<?> collection)
        {
            for (Object item : collection)
            {
                if (item != null && StringUtils.hasText(String.valueOf(item)))
                    result.add(String.valueOf(item).trim());
            }
        }
        else if (value != null && StringUtils.hasText(String.valueOf(value)))
        {
            result.addAll(List.of(String.valueOf(value).split(",")));
        }
        return Set.copyOf(result);
    }

    public record SessionContext(long userId, String username,
            Set<String> permissions, Instant expiresAt) {}

    public record SessionTicket(String session, long expiresInSeconds,
            long idleExpiresInSeconds, Instant expiresAt)
    {
        public Map<String, Object> asMap()
        {
            return Map.of(
                    "session", session,
                    "expiresInSeconds", expiresInSeconds,
                    "idleExpiresInSeconds", idleExpiresInSeconds,
                    "expiresAt", expiresAt.toString());
        }
    }
}
