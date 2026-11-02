package com.ruoyi.system.service.finance;

import com.ruoyi.system.service.python.PythonServiceProperties;
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
    private Duration readTimeout = Duration.ofHours(3);
    private String internalToken;
    /** 异步任务轮询间隔；总等待上限仍是 readTimeout。 */
    private Duration pollInterval = Duration.ofSeconds(10);
    /** 提交与单次轮询请求的超时。 */
    private Duration pollRequestTimeout = Duration.ofSeconds(30);

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

    public Duration getPollInterval() { return pollInterval; }
    public void setPollInterval(Duration pollInterval)
    {
        this.pollInterval = pollInterval;
    }

    public Duration getPollRequestTimeout() { return pollRequestTimeout; }
    public void setPollRequestTimeout(Duration pollRequestTimeout)
    {
        this.pollRequestTimeout = pollRequestTimeout;
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
