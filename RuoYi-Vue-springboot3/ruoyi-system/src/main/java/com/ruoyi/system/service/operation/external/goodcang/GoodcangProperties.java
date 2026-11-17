package com.ruoyi.system.service.operation.external.goodcang;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 谷仓 WMS API 配置属性。
 *
 * @author JMH
 */
@Component
@ConfigurationProperties(prefix = "goodcang")
public class GoodcangProperties
{
    /** 谷仓 API 基础地址 */
    private String endpoint = "https://oms.goodcang.net/public_open";

    /** Basic Auth app-token */
    private String appToken;

    /** Basic Auth app-key */
    private String appKey;

    /** 连接超时（毫秒） */
    private int connectTimeout = 30000;

    /** 读取超时（毫秒） */
    private int readTimeout = 30000;

    /** 同一应用实例内相邻谷仓请求的最小间隔（毫秒） */
    private long minRequestIntervalMs = 1200L;

    /** HTTP 429 最大重试次数，不包含首次请求 */
    private int maxRateLimitRetries = 6;

    /** HTTP 429 首次退避等待时间（毫秒） */
    private long rateLimitInitialBackoffMs = 3000L;

    /** HTTP 429 单次最大退避等待时间（毫秒） */
    private long rateLimitMaxBackoffMs = 30000L;

    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }

    public String getAppToken() { return appToken; }
    public void setAppToken(String appToken) { this.appToken = appToken; }

    public String getAppKey() { return appKey; }
    public void setAppKey(String appKey) { this.appKey = appKey; }

    public int getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(int connectTimeout) { this.connectTimeout = connectTimeout; }

    public int getReadTimeout() { return readTimeout; }
    public void setReadTimeout(int readTimeout) { this.readTimeout = readTimeout; }

    public long getMinRequestIntervalMs() { return minRequestIntervalMs; }
    public void setMinRequestIntervalMs(long minRequestIntervalMs) { this.minRequestIntervalMs = minRequestIntervalMs; }

    public int getMaxRateLimitRetries() { return maxRateLimitRetries; }
    public void setMaxRateLimitRetries(int maxRateLimitRetries) { this.maxRateLimitRetries = maxRateLimitRetries; }

    public long getRateLimitInitialBackoffMs() { return rateLimitInitialBackoffMs; }
    public void setRateLimitInitialBackoffMs(long rateLimitInitialBackoffMs) { this.rateLimitInitialBackoffMs = rateLimitInitialBackoffMs; }

    public long getRateLimitMaxBackoffMs() { return rateLimitMaxBackoffMs; }
    public void setRateLimitMaxBackoffMs(long rateLimitMaxBackoffMs) { this.rateLimitMaxBackoffMs = rateLimitMaxBackoffMs; }
}
