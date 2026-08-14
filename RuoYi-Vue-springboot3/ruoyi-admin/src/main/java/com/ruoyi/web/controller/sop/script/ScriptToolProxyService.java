package com.ruoyi.web.controller.sop.script;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.sop.AmazonImageUploadUserConfigService;
import com.ruoyi.system.service.sop.AmazonImageUploadUserConfigService.RuntimeConfig;
import com.ruoyi.web.controller.sop.script.ScriptToolSessionService.SessionPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.SequenceInputStream;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.URLDecoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;

/** 将ERP同源请求安全、流式地转发到Amazon主图上传Python子应用。 */
@Service
public class ScriptToolProxyService
{
    private static final String INTERNAL_TOKEN_HEADER = "X-Internal-Token";
    private static final String REQUEST_ID_HEADER = "X-Request-ID";
    private static final String USER_CONFIG_HEADER = "X-Ziniao-User-Config";
    private static final Set<String> INTERNAL_QUERY_PARAMS = Set.of(
            "erp_session", "api_base", "embedded");
    private static final Set<String> RESPONSE_HEADERS = Set.of(
            "content-type", "content-disposition", "content-length", "cache-control",
            "etag", "last-modified", "accept-ranges", "content-range", "x-request-id");

    private final ScriptToolPythonProperties properties;
    private final AmazonImageUploadUserConfigService userConfigService;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public ScriptToolProxyService(ScriptToolPythonProperties properties,
            AmazonImageUploadUserConfigService userConfigService,
            ObjectMapper objectMapper)
    {
        this.properties = properties;
        this.userConfigService = userConfigService;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofMillis(properties.getConnectTimeout()))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    public void forward(String targetPath, SessionPrincipal principal,
            HttpServletRequest request,
            HttpServletResponse response) throws IOException
    {
        String method = request.getMethod().toUpperCase(Locale.ROOT);
        if (!method.equals("GET") && !method.equals("POST") && !method.equals("HEAD"))
        {
            writeJsonError(response, 405, "脚本工具代理仅允许GET、POST和HEAD请求");
            return;
        }

        String requestId = StringUtils.hasText(request.getHeader(REQUEST_ID_HEADER))
                ? request.getHeader(REQUEST_ID_HEADER).trim()
                : UUID.randomUUID().toString();
        try
        {
            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(buildTargetUrl(targetPath, request.getQueryString())))
                    .timeout(Duration.ofMillis(properties.getReadTimeout()))
                    .header(REQUEST_ID_HEADER, requestId)
                    .header(HttpHeaders.ACCEPT, defaultHeader(request, HttpHeaders.ACCEPT, "*/*"));

            if (StringUtils.hasText(properties.getInternalToken()))
                builder.header(INTERNAL_TOKEN_HEADER, properties.getInternalToken().trim());
            if (principal.userId() != null)
                builder.header("X-Erp-User-ID", String.valueOf(principal.userId()));
            if (StringUtils.hasText(principal.username()))
                builder.header("X-Erp-User", principal.username().trim());
            if (requiresUserConfig(targetPath))
                addUserConfigHeader(builder, principal.userId());
            copyRequestHeader(request, builder, HttpHeaders.RANGE);
            copyRequestHeader(request, builder, HttpHeaders.IF_NONE_MATCH);
            copyRequestHeader(request, builder, HttpHeaders.IF_MODIFIED_SINCE);

            HttpRequest.BodyPublisher body = bodyPublisher(request, builder);
            builder.method(method, body);

            HttpResponse<InputStream> upstream = httpClient.send(
                    builder.build(), HttpResponse.BodyHandlers.ofInputStream());
            response.setStatus(upstream.statusCode());
            upstream.headers().map().forEach((name, values) -> {
                if (RESPONSE_HEADERS.contains(name.toLowerCase(Locale.ROOT)))
                    values.forEach(value -> response.addHeader(name, value));
            });
            response.setHeader("X-Content-Type-Options", "nosniff");
            response.setHeader("Referrer-Policy", "no-referrer");
            if (targetPath.equals("/") || targetPath.endsWith(".html"))
                response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
            try (InputStream bodyStream = upstream.body())
            {
                if (!method.equals("HEAD"))
                    bodyStream.transferTo(response.getOutputStream());
            }
            response.flushBuffer();
        }
        catch (InterruptedException e)
        {
            Thread.currentThread().interrupt();
            writeJsonError(response, 502, "主图上传服务调用被中断");
        }
        catch (IllegalArgumentException e)
        {
            writeJsonError(response, 400, e.getMessage());
        }
        catch (Exception e)
        {
            writeJsonError(response, 502, "主图上传Python服务不可用: "
                    + exceptionMessage(e));
        }
    }

    /** 账号快照只通过Java到本机Python的内部请求头传递。 */
    private void addUserConfigHeader(HttpRequest.Builder builder, Long userId)
            throws IOException
    {
        RuntimeConfig runtime = userConfigService.getRuntimeConfig(userId);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("source", "erp_user");
        payload.put("user_id", userId);
        payload.put("company", runtime.companyName());
        payload.put("username", runtime.accountName());
        payload.put("client_path", runtime.clientPath());
        payload.put("password", runtime.password());
        payload.put("password_cached", runtime.passwordCached());
        payload.put("password_expires_in_seconds", runtime.passwordExpiresInSeconds());
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(objectMapper.writeValueAsBytes(payload));
        builder.header(USER_CONFIG_HEADER, encoded);
    }

    private boolean requiresUserConfig(String targetPath)
    {
        return targetPath.equals("/api/config")
                || targetPath.equals("/api/shops/refresh")
                || targetPath.equals("/api/upload/start")
                || targetPath.equals("/api/upload/start_multi");
    }

    private String exceptionMessage(Exception exception)
    {
        Throwable current = exception;
        while (current.getCause() != null)
            current = current.getCause();
        String message = current.getMessage();
        return StringUtils.hasText(message)
                ? message : current.getClass().getSimpleName();
    }

    private HttpRequest.BodyPublisher bodyPublisher(HttpServletRequest request,
            HttpRequest.Builder builder)
    {
        if (request instanceof MultipartHttpServletRequest multipartRequest)
        {
            String boundary = "----JmhAmazonImageUpload"
                    + UUID.randomUUID().toString().replace("-", "");
            builder.header(HttpHeaders.CONTENT_TYPE, "multipart/form-data; boundary=" + boundary);
            return HttpRequest.BodyPublishers.ofInputStream(
                    () -> multipartInputStream(multipartRequest, boundary));
        }

        String contentType = request.getContentType();
        if (StringUtils.hasText(contentType))
            builder.header(HttpHeaders.CONTENT_TYPE, contentType);
        if (request.getMethod().equalsIgnoreCase("GET")
                || request.getMethod().equalsIgnoreCase("HEAD"))
            return HttpRequest.BodyPublishers.noBody();
        return HttpRequest.BodyPublishers.ofInputStream(() -> requestInputStream(request));
    }

    private InputStream multipartInputStream(MultipartHttpServletRequest request, String boundary)
    {
        try
        {
            List<InputStream> streams = new ArrayList<>();
            request.getParameterMap().forEach((name, values) -> {
                if (INTERNAL_QUERY_PARAMS.contains(name))
                    return;
                for (String value : values)
                {
                    streams.add(bytes("--" + boundary + "\r\n"
                            + "Content-Disposition: form-data; name=\"" + safe(name) + "\"\r\n"
                            + "Content-Type: text/plain; charset=UTF-8\r\n\r\n"
                            + (value == null ? "" : value) + "\r\n"));
                }
            });
            request.getMultiFileMap().forEach((name, files) -> {
                for (MultipartFile file : files)
                {
                    try
                    {
                        String filename = StringUtils.hasText(file.getOriginalFilename())
                                ? safe(file.getOriginalFilename()) : "image.bin";
                        String type = StringUtils.hasText(file.getContentType())
                                ? file.getContentType() : "application/octet-stream";
                        streams.add(bytes("--" + boundary + "\r\n"
                                + "Content-Disposition: form-data; name=\"" + safe(name)
                                + "\"; filename=\"" + filename + "\"\r\n"
                                + "Content-Type: " + type + "\r\n\r\n"));
                        streams.add(file.getInputStream());
                        streams.add(bytes("\r\n"));
                    }
                    catch (IOException e)
                    {
                        throw new UncheckedIOException(e);
                    }
                }
            });
            streams.add(bytes("--" + boundary + "--\r\n"));
            return new SequenceInputStream(Collections.enumeration(streams));
        }
        catch (UncheckedIOException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new IllegalStateException("构造主图上传请求失败", e);
        }
    }

    private String buildTargetUrl(String targetPath, String rawQuery)
    {
        String base = properties.getBaseUrl();
        while (base.endsWith("/"))
            base = base.substring(0, base.length() - 1);
        StringBuilder url = new StringBuilder(base).append(targetPath);
        if (StringUtils.hasText(rawQuery))
        {
            List<String> forwarded = new ArrayList<>();
            for (String part : rawQuery.split("&"))
            {
                String name = part;
                int equals = part.indexOf('=');
                if (equals >= 0)
                    name = part.substring(0, equals);
                String decodedName = URLDecoder.decode(name, StandardCharsets.UTF_8);
                if (!INTERNAL_QUERY_PARAMS.contains(decodedName))
                    forwarded.add(part);
            }
            if (!forwarded.isEmpty())
                url.append('?').append(String.join("&", forwarded));
        }
        return url.toString();
    }

    private String defaultHeader(HttpServletRequest request, String name, String fallback)
    {
        String value = request.getHeader(name);
        return StringUtils.hasText(value) ? value : fallback;
    }

    private void copyRequestHeader(HttpServletRequest request,
            HttpRequest.Builder builder, String name)
    {
        String value = request.getHeader(name);
        if (StringUtils.hasText(value))
            builder.header(name, value);
    }

    private InputStream requestInputStream(HttpServletRequest request)
    {
        try
        {
            return request.getInputStream();
        }
        catch (IOException e)
        {
            throw new UncheckedIOException(e);
        }
    }

    private InputStream bytes(String value)
    {
        return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
    }

    private String safe(String value)
    {
        return value.replace("\r", "").replace("\n", "").replace("\"", "'");
    }

    private void writeJsonError(HttpServletResponse response, int status, String message)
            throws IOException
    {
        if (response.isCommitted())
            return;
        response.reset();
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        String safeMessage = message == null ? "未知错误"
                : message.replace("\\", "\\\\").replace("\"", "\\\"")
                        .replace("\r", " ").replace("\n", " ");
        response.getWriter().write("{\"detail\":\"" + safeMessage + "\"}");
    }
}
