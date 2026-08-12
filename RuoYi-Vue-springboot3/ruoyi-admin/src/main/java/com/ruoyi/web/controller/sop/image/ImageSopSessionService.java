package com.ruoyi.web.controller.sop.image;

import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 为内嵌工作台签发仅能访问 Image-SOP 代理的临时会话。
 * 浏览器不会接触 Python 内部令牌，也不会把 ERP 登录令牌放进图片 URL。
 */
@Service
public class ImageSopSessionService
{
    private static final Duration SESSION_TTL = Duration.ofHours(8);
    private static final int TOKEN_BYTES = 32;
    private static final int MAX_SESSIONS_PER_USER = 12;

    private final SecureRandom secureRandom = new SecureRandom();
    private final ConcurrentHashMap<String, Session> sessions = new ConcurrentHashMap<>();

    public SessionTicket issue(Long userId, String username)
    {
        cleanupExpired();
        trimUserSessions(userId);
        byte[] random = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(random);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        Instant expiresAt = Instant.now().plus(SESSION_TTL);
        sessions.put(token, new Session(userId, username, expiresAt));
        return new SessionTicket(token, SESSION_TTL.toSeconds(), expiresAt);
    }

    public boolean validateAndTouch(String token)
    {
        if (!StringUtils.hasText(token))
            return false;
        Instant now = Instant.now();
        Session current = sessions.computeIfPresent(token, (key, value) -> {
            if (!value.expiresAt().isAfter(now))
                return null;
            return new Session(value.userId(), value.username(), now.plus(SESSION_TTL));
        });
        return current != null;
    }

    private void cleanupExpired()
    {
        Instant now = Instant.now();
        sessions.entrySet().removeIf(entry -> !entry.getValue().expiresAt().isAfter(now));
    }

    private void trimUserSessions(Long userId)
    {
        long active = sessions.values().stream()
                .filter(value -> java.util.Objects.equals(value.userId(), userId))
                .count();
        while (active >= MAX_SESSIONS_PER_USER)
        {
            String oldestToken = sessions.entrySet().stream()
                    .filter(entry -> java.util.Objects.equals(entry.getValue().userId(), userId))
                    .min(Map.Entry.comparingByValue(
                            java.util.Comparator.comparing(Session::expiresAt)))
                    .map(Map.Entry::getKey)
                    .orElse(null);
            if (oldestToken == null || sessions.remove(oldestToken) == null)
                return;
            active--;
        }
    }

    private record Session(Long userId, String username, Instant expiresAt) {}

    public record SessionTicket(String session, long expiresInSeconds, Instant expiresAt)
    {
        public Map<String, Object> asMap()
        {
            return Map.of(
                    "session", session,
                    "expiresInSeconds", expiresInSeconds,
                    "expiresAt", expiresAt.toString());
        }
    }
}
