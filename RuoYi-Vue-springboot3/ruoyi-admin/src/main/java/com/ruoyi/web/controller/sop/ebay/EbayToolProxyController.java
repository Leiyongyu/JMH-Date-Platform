package com.ruoyi.web.controller.sop.ebay;

import com.ruoyi.common.annotation.Anonymous;
import com.ruoyi.web.controller.sop.image.ImageSopSessionService;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * eBay价格工具反向代理。访问权由ERP短期会话控制，浏览器不能直接访问Python API。
 */
@Anonymous
@RestController
@RequestMapping("/sop/ebay-tool/proxy")
public class EbayToolProxyController
{
    static final String ROUTE_PREFIX = "/sop/ebay-tool/proxy";
    static final String REQUIRED_PERMISSION = "sop:ebayTool:use";
    private static final String SESSION_COOKIE = "JMH_EBAY_TOOL_SESSION";
    private static final Duration COOKIE_TTL = Duration.ofHours(1);
    private static final Set<String> ALLOWED_PATHS = Set.of(
            "/", "/index.html",
            "/api/scrape", "/api/scrape-file", "/api/check", "/api/export",
            "/api/sku/list", "/api/sku/add", "/api/sku/update",
            "/api/sku/delete", "/api/sku/lookup", "/api/sku/refresh",
            "/api/sku/import");
    private static final Pattern STATUS_PATH =
            Pattern.compile("^/api/status/[A-Za-z0-9_-]{1,128}$");

    private final ImageSopSessionService sessionService;
    private final EbayToolProxyService proxyService;

    public EbayToolProxyController(ImageSopSessionService sessionService,
            EbayToolProxyService proxyService)
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
                ? queryToken.trim() : sessionCookie(request);
        ImageSopSessionService.SessionContext session =
                sessionService.validateAndTouch(sessionToken, REQUIRED_PERMISSION);
        if (session == null)
        {
            writeUnauthorized(response);
            return;
        }

        String requestUri = request.getRequestURI();
        String contextPath = request.getContextPath() == null ? "" : request.getContextPath();
        String routeStart = contextPath + ROUTE_PREFIX;
        if (!requestUri.startsWith(routeStart))
        {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "无效的eBay工具代理路径");
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

        // eBay页面只支持api_base参数，不会为每个fetch追加erp_session。
        // 首次页面请求验证查询参数后写入HttpOnly Cookie；不显式设置Path，
        // 由浏览器按外部URL生成默认路径，从而兼容Nginx的/prod-api前缀。
        if (StringUtils.hasText(queryToken))
            setSessionCookie(request, response, sessionToken);
        proxyService.forward(targetPath, request, response, session);
    }

    static boolean isAllowedPath(String path)
    {
        if (!StringUtils.hasText(path))
            return false;
        String lower = path.toLowerCase();
        if (lower.contains("..") || lower.contains("%2e") || lower.contains("%2f")
                || lower.contains("%5c") || lower.contains("\\") || lower.indexOf('\0') >= 0)
            return false;
        return ALLOWED_PATHS.contains(path) || STATUS_PATH.matcher(path).matches();
    }

    private String sessionCookie(HttpServletRequest request)
    {
        Cookie[] cookies = request.getCookies();
        if (cookies == null)
            return null;
        for (Cookie cookie : cookies)
        {
            if (SESSION_COOKIE.equals(cookie.getName()))
                return cookie.getValue();
        }
        return null;
    }

    private void setSessionCookie(HttpServletRequest request, HttpServletResponse response,
            String token)
    {
        StringBuilder value = new StringBuilder(SESSION_COOKIE).append('=').append(token)
                .append("; Max-Age=").append(COOKIE_TTL.toSeconds())
                .append("; HttpOnly; SameSite=Strict");
        if (request.isSecure()
                || "https".equalsIgnoreCase(request.getHeader("X-Forwarded-Proto")))
            value.append("; Secure");
        response.addHeader("Set-Cookie", value.toString());
    }

    private void writeUnauthorized(HttpServletResponse response) throws IOException
    {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write(
                "{\"detail\":\"eBay价格工具会话无效或已过期，请刷新ERP页面\"}");
    }
}
