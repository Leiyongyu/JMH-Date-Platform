package com.ruoyi.web.controller.sop.image;

import com.ruoyi.common.annotation.Anonymous;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Image-SOP二进制反向代理。访问权由短期ERP专用会话控制，不能访问其他ERP接口。
 */
@Anonymous
@RestController
@RequestMapping("/sop/image-sop/proxy")
public class ImageSopProxyController
{
    private static final String ROUTE_PREFIX = "/sop/image-sop/proxy";

    private final ImageSopSessionService sessionService;
    private final ImageSopProxyService proxyService;

    public ImageSopProxyController(ImageSopSessionService sessionService,
            ImageSopProxyService proxyService)
    {
        this.sessionService = sessionService;
        this.proxyService = proxyService;
    }

    @RequestMapping({"", "/", "/**"})
    public void proxy(HttpServletRequest request, HttpServletResponse response)
            throws IOException
    {
        ImageSopSessionService.SessionContext session =
                sessionService.validateAndTouch(
                        request.getParameter("erp_session"),
                        ImageSopSessionService.IMAGE_SOP_PERMISSION);
        if (session == null)
        {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"detail\":\"图片SOP会话无效或已过期，请刷新ERP页面\"}");
            return;
        }

        String requestUri = request.getRequestURI();
        String contextPath = request.getContextPath() == null ? "" : request.getContextPath();
        String routeStart = contextPath + ROUTE_PREFIX;
        if (!requestUri.startsWith(routeStart))
        {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "无效的Image-SOP代理路径");
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
        proxyService.forward(targetPath, request, response, session);
    }

    private boolean isAllowedPath(String path)
    {
        String lower = path.toLowerCase();
        if (lower.contains("..") || lower.contains("%2e") || lower.contains("\\"))
            return false;
        return path.equals("/") || path.equals("/index.html")
                || path.startsWith("/api/") || path.startsWith("/web/");
    }
}
