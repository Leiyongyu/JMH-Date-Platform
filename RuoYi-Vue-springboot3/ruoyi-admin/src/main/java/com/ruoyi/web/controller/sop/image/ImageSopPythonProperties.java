package com.ruoyi.web.controller.sop.image;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Image-SOP Python 子应用连接配置。 */
@Component
@ConfigurationProperties(prefix = "image-sop.python")
public class ImageSopPythonProperties
{
    private String baseUrl = "http://127.0.0.1:8010/image-sop";
    private String workbenchUrl = "http://127.0.0.1:8010/script-tools/";
    private int connectTimeout = 5000;
    private int readTimeout = 900000;
    private String internalToken;

    public String getBaseUrl()
    {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl)
    {
        this.baseUrl = baseUrl;
    }

    public String getWorkbenchUrl()
    {
        return workbenchUrl;
    }

    public void setWorkbenchUrl(String workbenchUrl)
    {
        this.workbenchUrl = workbenchUrl;
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
