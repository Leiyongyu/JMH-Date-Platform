package com.ruoyi.web.controller.sop.customs;

import com.ruoyi.common.annotation.Anonymous;
import com.ruoyi.web.controller.sop.image.ImageSopSessionService;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Set;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 独立报关单系统的受控反向代理。
 * 浏览器只访问ERP同源地址，所有页面、静态资源和API请求均校验短期ERP会话。
 */
@Anonymous
@RestController
@RequestMapping(CustomsDeclarationProxyController.PREFIX)
public class CustomsDeclarationProxyController
{
    static final String PREFIX = "/sop/customs-declaration/proxy";
    static final String PERMISSION = "customs:declaration:query";
    static final String SESSION_COOKIE = "JMH_CUSTOMS_DECLARATION_SESSION";
    static final String BASE_COOKIE = "JMH_CUSTOMS_DECLARATION_BASE";

    private static final Set<String> GET_PATHS = Set.of(
            "/", "/index.html", "/api/search",
            "/static/app.js", "/static/icon/jiahao.svg",
            "/static/icon/jianhao.svg");
    private static final Set<String> POST_PATHS = Set.of(
            "/api/import", "/api/update-product",
            "/api/batch-query", "/api/export");

    private final ImageSopSessionService sessionService;
    private final CustomsDeclarationProxyService proxyService;

    public CustomsDeclarationProxyController(ImageSopSessionService sessionService,
            CustomsDeclarationProxyService proxyService)
    {
        this.sessionService = sessionService;
        this.proxyService = proxyService;
    }

    @RequestMapping({"", "/", "/**"})
    public void proxy(HttpServletRequest request, HttpServletResponse response)
            throws IOException
    {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Referrer-Policy", "no-referrer");

        String queryToken;
        String token;
        String publicBase;
        try
        {
            queryToken = query(request.getQueryString(), "erp_session");
            token = queryToken != null ? queryToken : cookie(request, SESSION_COOKIE);
            String queryBase = query(request.getQueryString(), "api_base");
            publicBase = normalizePublicBase(queryBase != null
                    ? queryBase : cookie(request, BASE_COOKIE));
        }
        catch (IllegalArgumentException e)
        {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST);
            return;
        }

        ImageSopSessionService.SessionContext session =
                sessionService.validateAndTouch(token, PERMISSION);
        if (session == null)
        {
            writeUnauthorized(response);
            return;
        }

        String contextPath = request.getContextPath() == null ? "" : request.getContextPath();
        String routeStart = contextPath + PREFIX;
        String requestUri = request.getRequestURI();
        if (!requestUri.startsWith(routeStart))
        {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        String targetPath = requestUri.substring(routeStart.length());
        if (targetPath.isEmpty())
            targetPath = "/";
        if (!allowed(request.getMethod(), targetPath))
        {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }

        if ("POST".equalsIgnoreCase(request.getMethod())
                && !"same-origin".equalsIgnoreCase(request.getHeader("Sec-Fetch-Site")))
        {
            response.sendError(HttpServletResponse.SC_FORBIDDEN);
            return;
        }

        if (publicBase == null)
            publicBase = contextPath + PREFIX;
        if (queryToken != null && ("/".equals(targetPath) || "/index.html".equals(targetPath)))
        {
            setScopedCookie(request, response, SESSION_COOKIE, token);
            setScopedCookie(request, response, BASE_COOKIE,
                    URLEncoder.encode(publicBase, StandardCharsets.UTF_8));
        }
        proxyService.forward(targetPath, request, response, session, publicBase);
    }

    static boolean allowed(String method, String path)
    {
        if (!StringUtils.hasText(method) || !StringUtils.hasText(path))
            return false;
        String lowerPath = path.toLowerCase(Locale.ROOT);
        if (lowerPath.contains("..") || lowerPath.contains("%2e")
                || lowerPath.contains("%2f") || lowerPath.contains("%5c")
                || lowerPath.contains("\\") || lowerPath.indexOf('\0') >= 0)
            return false;
        String upperMethod = method.toUpperCase(Locale.ROOT);
        return ("GET".equals(upperMethod) && GET_PATHS.contains(path))
                || ("HEAD".equals(upperMethod) && GET_PATHS.contains(path)
                        && !"/api/search".equals(path))
                || ("POST".equals(upperMethod) && POST_PATHS.contains(path));
    }

    static String query(String rawQuery, String expectedName)
    {
        if (!StringUtils.hasText(rawQuery))
            return null;
        String found = null;
        for (String part : rawQuery.split("&"))
        {
            String[] pair = part.split("=", 2);
            String name = URLDecoder.decode(pair[0], StandardCharsets.UTF_8);
            if (!expectedName.equals(name))
                continue;
            if (found != null)
                throw new IllegalArgumentException("Duplicate query parameter");
            found = pair.length == 2
                    ? URLDecoder.decode(pair[1], StandardCharsets.UTF_8) : "";
        }
        return found;
    }

    static String normalizePublicBase(String value)
    {
        if (!StringUtils.hasText(value))
            return null;
        String base = value.trim().replaceAll("/+$", "");
        String lower = base.toLowerCase(Locale.ROOT);
        if (!base.startsWith("/") || base.startsWith("//")
                || !base.endsWith(PREFIX) || base.contains("\\")
                || base.contains("?") || base.contains("#")
                || base.chars().anyMatch(ch -> ch < 0x21 || ch > 0x7e)
                || lower.contains("..") || lower.contains("%2e")
                || lower.contains("%2f") || lower.contains("%5c"))
            throw new IllegalArgumentException("Invalid public proxy base");
        return base;
    }

    private String cookie(HttpServletRequest request, String name)
    {
        String found = null;
        Cookie[] cookies = request.getCookies();
        if (cookies == null)
            return null;
        for (Cookie cookie : cookies)
        {
            if (!name.equals(cookie.getName()))
                continue;
            String value = BASE_COOKIE.equals(name)
                    ? URLDecoder.decode(cookie.getValue(), StandardCharsets.UTF_8)
                    : cookie.getValue();
            if (found != null && !found.equals(value))
                throw new IllegalArgumentException("Conflicting proxy cookies");
            found = value;
        }
        return found;
    }

    private void setScopedCookie(HttpServletRequest request, HttpServletResponse response,
            String name, String value)
    {
        StringBuilder cookie = new StringBuilder(name).append('=').append(value)
                .append("; HttpOnly; SameSite=Strict");
        if (request.isSecure()
                || "https".equalsIgnoreCase(request.getHeader("X-Forwarded-Proto")))
            cookie.append("; Secure");
        // 不显式设置Path，让浏览器按外部URL（含/prod-api等网关前缀）限定代理目录。
        response.addHeader("Set-Cookie", cookie.toString());
    }

    private void writeUnauthorized(HttpServletResponse response) throws IOException
    {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write(
                "{\"detail\":\"报关单生成器会话失效或无权限，请从插件菜单重新打开\"}");
    }
}
