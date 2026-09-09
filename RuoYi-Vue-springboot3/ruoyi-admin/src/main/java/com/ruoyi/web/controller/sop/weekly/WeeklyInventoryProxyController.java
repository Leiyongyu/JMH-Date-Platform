package com.ruoyi.web.controller.sop.weekly;

import com.ruoyi.common.annotation.Anonymous;
import com.ruoyi.system.service.finance.PythonPerformanceTaskProperties;
import com.ruoyi.web.controller.sop.image.ImageSopSessionService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.net.URLDecoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Explicit ERP session authorization on every request, including downloads. */
@Anonymous
@RestController
@RequestMapping("/sop/weekly-inventory/proxy")
public class WeeklyInventoryProxyController
{
    static final String PREFIX = "/sop/weekly-inventory/proxy";
    static final String PERMISSION = "sop:weeklyInventory:use";
    private final ImageSopSessionService sessions;
    private final PythonPerformanceTaskProperties properties;
    private final HttpClient client;

    public WeeklyInventoryProxyController(ImageSopSessionService sessions,
            PythonPerformanceTaskProperties properties)
    {
        this.sessions = sessions;
        this.properties = properties;
        this.client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER).build();
    }

    @RequestMapping({"", "/", "/**"})
    public void proxy(HttpServletRequest request, HttpServletResponse response) throws IOException
    {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Referrer-Policy", "no-referrer");
        String token;
        try { token = query(request.getQueryString(), "erp_session"); }
        catch (IllegalArgumentException e) { response.sendError(400); return; }
        // Never use getParameter(): it can consume form bodies before forwarding.
        if (sessions.validateAndTouch(token, PERMISSION) == null)
        {
            response.setStatus(403);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"detail\":\"会话失效或无周报权限，请从脚本中心重新打开\"}");
            return;
        }
        String root = request.getContextPath() + PREFIX;
        String uri = request.getRequestURI();
        if (!uri.startsWith(root)) { response.sendError(404); return; }
        String path = uri.substring(root.length());
        if (path.isEmpty() || path.equals("/")) path = "/index.html";
        if (!allowed(request.getMethod(), path)) { response.sendError(404); return; }
        String target = path.equals("/index.html") ? "/page" : path;
        try
        {
            if (path.equals("/files"))
            {
                String page = query(request.getQueryString(), "page");
                String limit = query(request.getQueryString(), "limit");
                if ((page != null && !page.matches("[0-9]{1,8}"))
                        || (limit != null && !limit.matches("[0-9]{1,3}")))
                { response.sendError(400); return; }
                target += "?page=" + (page == null ? "1" : page)
                        + "&limit=" + (limit == null ? "20" : limit);
            }
            String base = properties.getBaseUrl().replaceAll("/+$", "");
            HttpRequest.Builder builder = HttpRequest.newBuilder(
                    URI.create(base + "/api/v1/weekly-inventory" + target))
                    .timeout(Duration.ofSeconds(120))
                    .header("X-Request-Id", "weekly-proxy-" + UUID.randomUUID());
            if (properties.getInternalToken() != null && !properties.getInternalToken().isBlank())
                builder.header("X-Internal-Token", properties.getInternalToken());
            // The only POST is a parameterless background command; no user body is forwarded.
            if (request.getMethod().equals("POST")) builder.POST(HttpRequest.BodyPublishers.noBody());
            else builder.GET();
            HttpResponse<java.io.InputStream> upstream = client.send(builder.build(), HttpResponse.BodyHandlers.ofInputStream());
            try (java.io.InputStream stream = upstream.body())
            {
                response.setStatus(upstream.statusCode());
                for (String name : new String[]{"Content-Type", "Content-Disposition", "Content-Length"})
                    upstream.headers().firstValue(name).ifPresent(value -> response.setHeader(name, value));
                stream.transferTo(response.getOutputStream());
            }
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            if (!response.isCommitted()) response.sendError(502, "周报服务连接中断");
        }
        catch (Exception e)
        {
            if (!response.isCommitted()) response.sendError(502, "周报服务暂不可用，请检查Python服务及内部令牌配置");
        }
    }

    static boolean allowed(String method, String path)
    {
        return ("POST".equals(method) && "/run".equals(path))
                || ("GET".equals(method) && ("/index.html".equals(path) || "/files".equals(path)
                || path.matches("/files/[1-9][0-9]{0,18}/download")));
    }

    static String query(String raw, String name)
    {
        if (raw == null) return null;
        String found = null;
        for (String part : raw.split("&"))
        {
            String[] pair = part.split("=", 2);
            if (URLDecoder.decode(pair[0], StandardCharsets.UTF_8).equals(name))
            {
                if (found != null) throw new IllegalArgumentException("Duplicate parameter");
                found = pair.length == 2 ? URLDecoder.decode(pair[1], StandardCharsets.UTF_8) : "";
            }
        }
        return found;
    }
}
