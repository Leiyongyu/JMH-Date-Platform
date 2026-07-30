package com.ruoyi.system.service.finance;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Python 绩效排名服务连接配置。 */
@Component
@ConfigurationProperties(prefix = "performance.python")
public class PerformancePythonProperties
{
    private String baseUrl = "http://127.0.0.1:8010/api/v1/finance";
    private int connectTimeout = 5000;
    private int readTimeout = 300000;

    public String getBaseUrl()
    {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl)
    {
        this.baseUrl = baseUrl;
    }

    public int getConnectTimeout()
    {
        return connectTimeout;
    }

    public void setConnectTimeout(int connectTimeout)
    {
        this.connectTimeout = connectTimeout;
    }

    public int getReadTimeout()
    {
        return readTimeout;
    }

    public void setReadTimeout(int readTimeout)
    {
        this.readTimeout = readTimeout;
    }
}
