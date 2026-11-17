package com.ruoyi.web.controller.sop.customs;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** 独立报关单系统的服务端连接配置。 */
@Component
@ConfigurationProperties(prefix = "customs-declaration.legacy")
public class CustomsDeclarationLegacyProperties
{
    private String baseUrl = "http://127.0.0.1:8010/customs-declaration";
    private int connectTimeout = 5000;
    private int readTimeout = 120000;
    private String internalToken;

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

    public String getInternalToken()
    {
        return internalToken;
    }

    public void setInternalToken(String internalToken)
    {
        this.internalToken = internalToken;
    }
}
