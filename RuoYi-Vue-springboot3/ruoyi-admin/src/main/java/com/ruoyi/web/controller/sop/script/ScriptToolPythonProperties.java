package com.ruoyi.web.controller.sop.script;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Amazon主图上传 Python 子应用连接配置。 */
@Component
@ConfigurationProperties(prefix = "script-tools.python")
public class ScriptToolPythonProperties
{
    private String baseUrl = "http://127.0.0.1:8010/amazon-image-upload";
    private int connectTimeout = 5000;
    private int readTimeout = 10800000;
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
