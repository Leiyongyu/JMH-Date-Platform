package com.ruoyi.web.controller.sop.image;

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
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;

/** 将 ERP 同源请求安全、流式地转发到 Python Image-SOP 子应用。 */
@Service
public class ImageSopProxyService
{
    private static final String INTERNAL_TOKEN_HEADER = "X-Internal-Token";
    private static final String REQUEST_ID_HEADER = "X-Request-ID";
    private static final String ERP_USER_ID_HEADER = "X-ERP-User-ID";
    private static final String ERP_USERNAME_HEADER = "X-ERP-Username-B64";
    private static final Set<String> INTERNAL_QUERY_PARAMS = Set.of(
            "erp_session", "api_base", "embedded");
    private static final Set<String> RESPONSE_HEADERS = Set.of(
            "content-type", "content-disposition", "content-length", "cache-control",
            "etag", "last-modified", "accept-ranges", "content-range", "x-request-id");

    private final ImageSopPythonProperties properties;
    private final HttpClient httpClient;

    public ImageSopProxyService(ImageSopPythonProperties properties)
    {
        this.properties = properties;
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofMillis(properties.getConnectTimeout()))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    public void forward(String targetPath, HttpServletRequest request,
            HttpServletResponse response,
            ImageSopSessionService.SessionContext session) throws IOException
    {
        String method = request.getMethod().toUpperCase(Locale.ROOT);
        if (!method.equals("GET") && !method.equals("POST") && !method.equals("HEAD"))
        {
            writeJsonError(response, 405, "Image-SOP代理仅允许GET、POST和HEAD请求");
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
            builder.header(ERP_USER_ID_HEADER, String.valueOf(session.userId()));
            builder.header(ERP_USERNAME_HEADER, Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(session.username().getBytes(StandardCharsets.UTF_8)));
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
            writeJsonError(response, 502, "Image-SOP服务调用被中断");
        }
        catch (IllegalArgumentException e)
        {
            writeJsonError(response, 400, e.getMessage());
        }
        catch (Exception e)
        {
            writeJsonError(response, 502, "Image-SOP Python服务不可用: " + e.getMessage());
        }
    }

    private HttpRequest.BodyPublisher bodyPublisher(HttpServletRequest request,
            HttpRequest.Builder builder)
    {
        if (request instanceof MultipartHttpServletRequest multipartRequest)
        {
            String boundary = "----JmhImageSop" + UUID.randomUUID().toString().replace("-", "");
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
            throw new IllegalStateException("构造Image-SOP上传请求失败", e);
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
