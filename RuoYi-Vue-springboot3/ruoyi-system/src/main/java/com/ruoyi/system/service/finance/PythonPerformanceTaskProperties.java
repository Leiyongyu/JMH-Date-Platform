package com.ruoyi.system.service.finance;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Python绩效内部任务接口配置。 */
@Component
@ConfigurationProperties(prefix = "jmh.python-performance")
public class PythonPerformanceTaskProperties implements PythonServiceProperties
{
    private String baseUrl = "http://127.0.0.1:8010";
    private Duration connectTimeout = Duration.ofSeconds(3);
    private Duration readTimeout = Duration.ofMinutes(30);
    private String internalToken;

    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout)
    {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() { return readTimeout; }
    public void setReadTimeout(Duration readTimeout)
    {
        this.readTimeout = readTimeout;
    }

    public String getInternalToken() { return internalToken; }
    public void setInternalToken(String internalToken)
    {
        this.internalToken = internalToken;
    }

    @Override
    public int getConnectTimeoutMillis()
    {
        return (int) connectTimeout.toMillis();
    }

    @Override
    public int getReadTimeoutMillis()
    {
        return (int) readTimeout.toMillis();
    }
}
