package com.ruoyi.system.service.finance;

/** Python 内网服务连接配置的统一访问接口。 */
public interface PythonServiceProperties
{
    String getBaseUrl();

    int getConnectTimeoutMillis();

    int getReadTimeoutMillis();

    /** 内部接口令牌；未配置时不发送 X-Internal-Token 请求头。 */
    default String getInternalToken()
    {
        return null;
    }
}
