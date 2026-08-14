package com.ruoyi.web.controller.sop.script;

import com.ruoyi.common.annotation.Anonymous;
import com.ruoyi.web.controller.sop.script.ScriptToolSessionService.SessionPrincipal;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Amazon主图上传子应用的同源白名单代理。 */
@Anonymous
@RestController
@RequestMapping("/sop/script-tools/amazon-image-upload/proxy")
public class ScriptToolProxyController
{
    private static final String ROUTE_PREFIX =
            "/sop/script-tools/amazon-image-upload/proxy";
    private static final String SESSION_COOKIE = "jmh_amz_image_upload_session";

    private final ScriptToolSessionService sessionService;
    private final ScriptToolProxyService proxyService;

    public ScriptToolProxyController(ScriptToolSessionService sessionService,
            ScriptToolProxyService proxyService)
    {
        this.sessionService = sessionService;
        this.proxyService = proxyService;
    }

    @RequestMapping({"", "/", "/**"})
    public void proxy(HttpServletRequest request, HttpServletResponse response)
            throws IOException
    {
        String queryToken = request.getParameter("erp_session");
        String sessionToken = StringUtils.hasText(queryToken)
                ? queryToken : cookieValue(request, SESSION_COOKIE);
        SessionPrincipal principal = sessionService.resolveAndTouch(sessionToken);
        if (principal == null)
        {
            writeUnauthorized(response);
            return;
        }
        if (StringUtils.hasText(queryToken))
            issueSessionCookie(request, response, queryToken);

        String requestUri = request.getRequestURI();
        String contextPath = request.getContextPath() == null ? "" : request.getContextPath();
        String routeStart = contextPath + ROUTE_PREFIX;
        if (!requestUri.startsWith(routeStart))
        {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "无效的脚本代理路径");
            return;
        }
        String targetPath = requestUri.substring(routeStart.length());
        if (targetPath.isEmpty())
            targetPath = "/";
        if (!isAllowedPath(targetPath))
        {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        proxyService.forward(targetPath, principal, request, response);
    }

    private boolean isAllowedPath(String path)
    {
        String lower = path.toLowerCase();
        if (lower.contains("..") || lower.contains("%2e") || lower.contains("\\"))
            return false;
        return path.equals("/") || path.equals("/index.html")
                || path.startsWith("/api/") || path.startsWith("/web/");
    }

    private String cookieValue(HttpServletRequest request, String name)
    {
        Cookie[] cookies = request.getCookies();
        if (cookies == null)
            return null;
        for (Cookie cookie : cookies)
            if (name.equals(cookie.getName()))
                return cookie.getValue();
        return null;
    }

    private void issueSessionCookie(HttpServletRequest request,
            HttpServletResponse response, String token)
    {
        boolean secure = request.isSecure()
                || "https".equalsIgnoreCase(request.getHeader("X-Forwarded-Proto"));
        ResponseCookie cookie = ResponseCookie.from(SESSION_COOKIE, token)
                .httpOnly(true)
                .secure(secure)
                .sameSite("Strict")
                // 前端通常通过 /prod-api 或 /dev-api 反代，使用根路径才能让
                // 后续静态资源/API请求携带此专用Cookie；其他接口不会读取它。
                .path("/")
                .maxAge(8 * 60 * 60)
                .build();
        response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
    }

    private void writeUnauthorized(HttpServletResponse response) throws IOException
    {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write(
                "{\"detail\":\"脚本工具会话无效或已过期，请从ERP脚本菜单重新打开\"}");
    }
}
