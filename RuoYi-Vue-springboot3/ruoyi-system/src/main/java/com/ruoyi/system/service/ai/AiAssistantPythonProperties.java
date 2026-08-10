package com.ruoyi.system.service.ai;

import com.ruoyi.system.service.finance.PythonServiceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Python AI助手服务连接配置。 */
@Component
@ConfigurationProperties(prefix = "ai-assistant.python")
public class AiAssistantPythonProperties implements PythonServiceProperties
{
    private String baseUrl = "http://127.0.0.1:8010";
    private int connectTimeout = 5000;
    private int readTimeout = 200000;
    private String internalToken;

    @Override
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

    @Override
    public int getConnectTimeoutMillis()
    {
        return connectTimeout;
    }

    @Override
    public int getReadTimeoutMillis()
    {
        return readTimeout;
    }

    @Override
    public String getInternalToken()
    {
        return internalToken;
    }

    public void setInternalToken(String internalToken)
    {
        this.internalToken = internalToken;
    }
}
