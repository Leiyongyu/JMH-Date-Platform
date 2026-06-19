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
}
