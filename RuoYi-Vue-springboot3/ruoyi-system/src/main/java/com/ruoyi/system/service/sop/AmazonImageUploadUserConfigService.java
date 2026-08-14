package com.ruoyi.system.service.sop;

import com.ruoyi.common.core.redis.RedisCache;
import com.ruoyi.system.domain.sop.AmazonImageUploadUserConfig;
import com.ruoyi.system.mapper.sop.AmazonImageUploadUserConfigMapper;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** 用户级紫鸟配置：非敏感项落MySQL，密码只在Redis保留8小时。 */
@Service
public class AmazonImageUploadUserConfigService
{
    private static final String PASSWORD_CACHE_PREFIX =
            "sop:amazon-image-upload:ziniao-password:";
    private static final int PASSWORD_TTL_HOURS = 8;

    private final AmazonImageUploadUserConfigMapper configMapper;
    private final RedisCache redisCache;

    public AmazonImageUploadUserConfigService(
            AmazonImageUploadUserConfigMapper configMapper,
            RedisCache redisCache)
    {
        this.configMapper = configMapper;
        this.redisCache = redisCache;
    }

    public Map<String, Object> getConfigStatus(Long userId)
    {
        RuntimeConfig runtime = getRuntimeConfig(userId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("companyName", runtime.companyName());
        result.put("accountName", runtime.accountName());
        result.put("clientPath", runtime.clientPath());
        result.put("configured", runtime.nonSecretConfigured());
        result.put("passwordCached", runtime.passwordCached());
        result.put("passwordExpiresInSeconds", runtime.passwordExpiresInSeconds());
        result.put("ready", runtime.ready());
        return result;
    }

    /**
     * 返回运行时快照。此对象仅用于Java到本机Python的内部转发，
     * 禁止作为Controller返回值。
     */
    public RuntimeConfig getRuntimeConfig(Long userId)
    {
        AmazonImageUploadUserConfig stored = userId == null
                ? null : configMapper.selectByUserId(userId);
        String password = userId == null ? null
                : redisCache.getCacheObject(passwordKey(userId));
        long expires = userId == null ? 0 : redisCache.getExpire(passwordKey(userId));

        String companyName = stored == null ? "" : safe(stored.getCompanyName());
        String accountName = stored == null ? "" : safe(stored.getAccountName());
        String clientPath = stored == null ? "" : safe(stored.getClientPath());
        String runtimePassword = safe(password);
        boolean nonSecretConfigured = StringUtils.hasText(companyName)
                && StringUtils.hasText(accountName) && StringUtils.hasText(clientPath);
        boolean passwordCached = StringUtils.hasText(runtimePassword) && expires > 0;
        return new RuntimeConfig(
                companyName,
                accountName,
                clientPath,
                passwordCached ? runtimePassword : "",
                nonSecretConfigured,
                passwordCached,
                Math.max(0, expires));
    }

    public void requireReady(Long userId)
    {
        RuntimeConfig runtime = getRuntimeConfig(userId);
        if (!runtime.nonSecretConfigured())
            throw new IllegalStateException("请先配置紫鸟公司名、账号和客户端路径");
        if (!runtime.passwordCached())
            throw new IllegalStateException("紫鸟密码未输入或已超过8小时，请重新输入");
    }

    @Transactional(rollbackFor = Exception.class)
    public void saveConfig(Long userId, String operator,
            String companyName, String accountName, String clientPath, String password)
    {
        if (userId == null)
            throw new IllegalArgumentException("无法识别当前ERP用户");

        String normalizedCompany = required(companyName, "公司名", 128);
        String normalizedAccount = required(accountName, "紫鸟账号", 128);
        String normalizedPath = required(clientPath, "紫鸟客户端路径", 500);
        if (!normalizedPath.toLowerCase().replace('/', '\\').endsWith("\\ziniao.exe"))
            throw new IllegalArgumentException("紫鸟客户端路径必须指向 ziniao.exe");
        // 密码可能合法包含首尾空格，只校验但不做trim或其他改写。
        String normalizedPassword = password == null ? "" : password;
        if (normalizedPassword.length() > 512)
            throw new IllegalArgumentException("紫鸟密码长度不能超过512个字符");

        AmazonImageUploadUserConfig existing = configMapper.selectByUserId(userId);
        boolean identityChanged = existing == null
                || !Objects.equals(normalizedCompany, trim(existing.getCompanyName()))
                || !Objects.equals(normalizedAccount, trim(existing.getAccountName()));
        String cachedPassword = redisCache.getCacheObject(passwordKey(userId));
        if (!StringUtils.hasText(normalizedPassword)
                && (identityChanged || !StringUtils.hasText(cachedPassword)))
        {
            throw new IllegalArgumentException("请输入紫鸟密码；密码只在Redis中保留8小时");
        }

        AmazonImageUploadUserConfig config = existing == null
                ? new AmazonImageUploadUserConfig() : existing;
        config.setUserId(userId);
        config.setCompanyName(normalizedCompany);
        config.setAccountName(normalizedAccount);
        config.setClientPath(normalizedPath);
        if (existing == null)
        {
            config.setCreateBy(safeOperator(operator));
            configMapper.insertConfig(config);
        }
        else
        {
            config.setUpdateBy(safeOperator(operator));
            configMapper.updateConfig(config);
        }

        if (StringUtils.hasText(normalizedPassword))
        {
            redisCache.setCacheObject(passwordKey(userId), normalizedPassword,
                    PASSWORD_TTL_HOURS, TimeUnit.HOURS);
        }
    }

    public void clearPassword(Long userId)
    {
        if (userId != null)
            redisCache.deleteObject(passwordKey(userId));
    }

    private String passwordKey(Long userId)
    {
        return PASSWORD_CACHE_PREFIX + userId;
    }

    private String required(String value, String label, int maxLength)
    {
        String normalized = trim(value);
        if (!StringUtils.hasText(normalized))
            throw new IllegalArgumentException("请输入" + label);
        if (normalized.length() > maxLength)
            throw new IllegalArgumentException(label + "长度不能超过" + maxLength + "个字符");
        return normalized;
    }

    private String safeOperator(String value)
    {
        String result = trim(value);
        return result.length() <= 64 ? result : result.substring(0, 64);
    }

    private String safe(String value)
    {
        return value == null ? "" : value;
    }

    private String trim(String value)
    {
        return value == null ? "" : value.trim();
    }

    public record RuntimeConfig(
            String companyName,
            String accountName,
            String clientPath,
            String password,
            boolean nonSecretConfigured,
            boolean passwordCached,
            long passwordExpiresInSeconds)
    {
        public boolean ready()
        {
            return nonSecretConfigured && passwordCached;
        }
    }
}
