package com.ruoyi.web.controller.sop.script;

import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** 为脚本工具代理签发有作用域、可续期的临时ERP会话。 */
@Service
public class ScriptToolSessionService
{
    private static final Duration SESSION_TTL = Duration.ofHours(8);
    private static final int TOKEN_BYTES = 32;
    private static final int MAX_SESSIONS_PER_USER = 8;

    private final SecureRandom secureRandom = new SecureRandom();
    private final ConcurrentHashMap<String, SessionPrincipal> sessions =
            new ConcurrentHashMap<>();

    public SessionTicket issue(Long userId, String username)
    {
        cleanupExpired();
        trimUserSessions(userId);
        byte[] random = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(random);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        Instant expiresAt = Instant.now().plus(SESSION_TTL);
        sessions.put(token, new SessionPrincipal(userId, username, expiresAt));
        return new SessionTicket(token, SESSION_TTL.toSeconds(), expiresAt);
    }

    public SessionPrincipal resolveAndTouch(String token)
    {
        if (!StringUtils.hasText(token))
            return null;
        Instant now = Instant.now();
        return sessions.computeIfPresent(token, (key, value) -> {
            if (!value.expiresAt().isAfter(now))
                return null;
            return new SessionPrincipal(
                    value.userId(), value.username(), now.plus(SESSION_TTL));
        });
    }

    private void cleanupExpired()
    {
        Instant now = Instant.now();
        sessions.entrySet().removeIf(entry -> !entry.getValue().expiresAt().isAfter(now));
    }

    private void trimUserSessions(Long userId)
    {
        long active = sessions.values().stream()
                .filter(value -> Objects.equals(value.userId(), userId)).count();
        while (active >= MAX_SESSIONS_PER_USER)
        {
            String oldestToken = sessions.entrySet().stream()
                    .filter(entry -> Objects.equals(entry.getValue().userId(), userId))
                    .min(Map.Entry.comparingByValue(
                            java.util.Comparator.comparing(SessionPrincipal::expiresAt)))
                    .map(Map.Entry::getKey).orElse(null);
            if (oldestToken == null || sessions.remove(oldestToken) == null)
                return;
            active--;
        }
    }

    public record SessionPrincipal(Long userId, String username, Instant expiresAt) {}

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
