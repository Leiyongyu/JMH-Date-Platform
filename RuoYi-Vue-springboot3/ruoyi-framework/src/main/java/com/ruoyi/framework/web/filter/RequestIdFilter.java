package com.ruoyi.framework.web.filter;

import java.io.IOException;
import java.util.UUID;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 请求链路ID过滤器：读取请求头 X-Request-ID，缺失时生成，写入 MDC 并回写响应头，
 * 供业务日志与 Python 内网客户端（X-Request-ID）全链路串联使用。
 */
public class RequestIdFilter extends OncePerRequestFilter
{
    public static final String REQUEST_ID_HEADER = "X-Request-ID";
    public static final String REQUEST_ID_KEY = "request_id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException
    {
        String requestId = request.getHeader(REQUEST_ID_HEADER);
        if (!StringUtils.hasText(requestId))
            requestId = UUID.randomUUID().toString();
        MDC.put(REQUEST_ID_KEY, requestId);
        response.setHeader(REQUEST_ID_HEADER, requestId);
        try
        {
            filterChain.doFilter(request, response);
        }
        finally
        {
            MDC.remove(REQUEST_ID_KEY);
        }
    }
}
