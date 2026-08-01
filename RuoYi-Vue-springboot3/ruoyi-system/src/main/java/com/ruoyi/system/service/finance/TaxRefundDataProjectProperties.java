package com.ruoyi.system.service.finance;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** 当前 Date-Project 外汇退税服务配置。 */
@Component
@ConfigurationProperties(prefix = "tax-refund.data-project")
public class TaxRefundDataProjectProperties
{
    private String baseUrl = "http://127.0.0.1:8010";
    private int connectTimeout = 5000;
    private int readTimeout = 600000;

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
