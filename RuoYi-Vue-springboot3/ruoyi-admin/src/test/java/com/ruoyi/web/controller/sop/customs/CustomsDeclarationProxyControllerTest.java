package com.ruoyi.web.controller.sop.customs;

import com.ruoyi.web.controller.sop.image.ImageSopSessionService;
import jakarta.servlet.http.Cookie;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class CustomsDeclarationProxyControllerTest
{
    private static final String TOKEN = "valid-customs-session";
    private static final String PUBLIC_BASE = "/prod-api/sop/customs-declaration/proxy";

    private ImageSopSessionService validSessions()
    {
        ImageSopSessionService sessions = mock(ImageSopSessionService.class);
        when(sessions.validateAndTouch(TOKEN, CustomsDeclarationProxyController.PERMISSION))
                .thenReturn(new ImageSopSessionService.SessionContext(
                        7L, "tester", Set.of(CustomsDeclarationProxyController.PERMISSION),
                        Instant.now().plusSeconds(3600)));
        return sessions;
    }

    @Test
    void springCanConstructProxyServiceWithItsProductionConstructor()
    {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext())
        {
            context.register(CustomsDeclarationLegacyProperties.class,
                    CustomsDeclarationProxyService.class);
            context.refresh();
            assertNotNull(context.getBean(CustomsDeclarationProxyService.class));
        }
    }

    @Test
    void launchSetsScopedCookiesAndForwardsExistingPage() throws Exception
    {
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                validSessions(), proxyService);
        MockHttpServletRequest request = new MockHttpServletRequest(
                "GET", CustomsDeclarationProxyController.PREFIX + "/index.html");
        request.setQueryString("erp_session=" + TOKEN
                + "&api_base=%2Fprod-api%2Fsop%2Fcustoms-declaration%2Fproxy");
        request.addHeader("X-Forwarded-Proto", "https");
        MockHttpServletResponse response = new MockHttpServletResponse();

        controller.proxy(request, response);

        assertEquals(200, response.getStatus());
        List<String> cookies = List.copyOf(response.getHeaders("Set-Cookie"));
        assertEquals(3, cookies.size());
        assertTrue(cookies.stream().anyMatch(value -> value.startsWith(
                CustomsDeclarationProxyController.SESSION_COOKIE + "=" + TOKEN)));
        assertEquals(2, cookies.stream().filter(value -> value.contains("HttpOnly")).count());
        assertTrue(cookies.stream().allMatch(value -> value.contains("SameSite=Strict")
                && value.contains("Secure")
                && !value.contains("Path=") && !value.contains("Domain=")));
        assertTrue(cookies.stream().anyMatch(value -> value.startsWith(
                CustomsDeclarationProxyController.CSRF_COOKIE + "=")
                && !value.contains("HttpOnly")
                && value.contains("SameSite=Strict") && value.contains("Secure")
                && !value.contains("Path=") && !value.contains("Domain=")));
        verify(proxyService).forward(eq("/index.html"), eq(request), eq(response),
                any(ImageSopSessionService.SessionContext.class), eq(PUBLIC_BASE));
    }

    @Test
    void cookieRefreshKeepsGatewayPrefixForStaticRewrite() throws Exception
    {
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                validSessions(), proxyService);
        MockHttpServletRequest request = new MockHttpServletRequest(
                "GET", CustomsDeclarationProxyController.PREFIX + "/static/app.js");
        request.setCookies(
                new Cookie(CustomsDeclarationProxyController.SESSION_COOKIE, TOKEN),
                new Cookie(CustomsDeclarationProxyController.BASE_COOKIE,
                        "%2Fprod-api%2Fsop%2Fcustoms-declaration%2Fproxy"));
        MockHttpServletResponse response = new MockHttpServletResponse();

        controller.proxy(request, response);

        assertEquals(200, response.getStatus());
        verify(proxyService).forward(eq("/static/app.js"), eq(request), eq(response),
                any(ImageSopSessionService.SessionContext.class), eq(PUBLIC_BASE));
    }

    @Test
    void missingOrForgedSessionNeverReachesLegacyService() throws Exception
    {
        ImageSopSessionService sessions = mock(ImageSopSessionService.class);
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                sessions, proxyService);
        for (String token : new String[]{null, "forged"})
        {
            MockHttpServletRequest request = new MockHttpServletRequest(
                    "GET", CustomsDeclarationProxyController.PREFIX + "/index.html");
            if (token != null)
                request.setQueryString("erp_session=" + token);
            MockHttpServletResponse response = new MockHttpServletResponse();
            controller.proxy(request, response);
            assertEquals(403, response.getStatus());
            verify(sessions).validateAndTouch(token,
                    CustomsDeclarationProxyController.PERMISSION);
        }
        verifyNoInteractions(proxyService);
    }

    @Test
    void postRequiresSameOriginAndNeverAllowsInitDatabase() throws Exception
    {
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                validSessions(), proxyService);
        MockHttpServletRequest crossSite = new MockHttpServletRequest(
                "POST", CustomsDeclarationProxyController.PREFIX + "/api/export");
        crossSite.setCookies(new Cookie(CustomsDeclarationProxyController.SESSION_COOKIE, TOKEN));
        crossSite.addHeader("Sec-Fetch-Site", "cross-site");
        MockHttpServletResponse forbidden = new MockHttpServletResponse();
        controller.proxy(crossSite, forbidden);
        assertEquals(403, forbidden.getStatus());
        assertTrue(forbidden.getContentAsString().contains("请求来源校验失败"));

        assertFalse(CustomsDeclarationProxyController.allowed("POST", "/api/init-db"));
        assertFalse(CustomsDeclarationProxyController.allowed("GET", "/api/export"));
        assertFalse(CustomsDeclarationProxyController.allowed("GET", "/static/../app.py"));
        assertTrue(CustomsDeclarationProxyController.allowed("GET", "/api/search"));
        assertTrue(CustomsDeclarationProxyController.allowed("POST", "/api/export"));
        verifyNoInteractions(proxyService);
    }

    @Test
    void postFallsBackToForwardedOriginWhenFetchMetadataIsStripped() throws Exception
    {
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                validSessions(), proxyService);
        MockHttpServletRequest request = new MockHttpServletRequest(
                "POST", CustomsDeclarationProxyController.PREFIX + "/api/export");
        request.setCookies(new Cookie(CustomsDeclarationProxyController.SESSION_COOKIE, TOKEN));
        request.addHeader("Origin", "https://erp.example.com");
        request.addHeader("X-Forwarded-Proto", "https");
        request.addHeader("X-Forwarded-Host", "erp.example.com");
        MockHttpServletResponse response = new MockHttpServletResponse();

        controller.proxy(request, response);

        assertEquals(200, response.getStatus());
        verify(proxyService).forward(eq("/api/export"), eq(request), eq(response),
                any(ImageSopSessionService.SessionContext.class),
                eq(CustomsDeclarationProxyController.PREFIX));
    }

    @Test
    void postAcceptsMatchingCsrfCookieAndHeaderBehindRewritingGateway() throws Exception
    {
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                validSessions(), proxyService);
        String csrf = "random-csrf-token-from-launch";
        MockHttpServletRequest request = new MockHttpServletRequest(
                "POST", CustomsDeclarationProxyController.PREFIX + "/api/export");
        request.setCookies(
                new Cookie(CustomsDeclarationProxyController.SESSION_COOKIE, TOKEN),
                new Cookie(CustomsDeclarationProxyController.CSRF_COOKIE, csrf));
        request.addHeader(CustomsDeclarationProxyController.CSRF_HEADER, csrf);
        request.addHeader("Sec-Fetch-Site", "same-site");
        request.addHeader("Origin", "https://gateway-rewritten.invalid");
        MockHttpServletResponse response = new MockHttpServletResponse();

        controller.proxy(request, response);

        assertEquals(200, response.getStatus());
        verify(proxyService).forward(eq("/api/export"), eq(request), eq(response),
                any(ImageSopSessionService.SessionContext.class),
                eq(CustomsDeclarationProxyController.PREFIX));
    }

    @Test
    void postRejectsMismatchedCsrfHeaderAndCookie() throws Exception
    {
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                validSessions(), proxyService);
        MockHttpServletRequest request = new MockHttpServletRequest(
                "POST", CustomsDeclarationProxyController.PREFIX + "/api/export");
        request.setCookies(
                new Cookie(CustomsDeclarationProxyController.SESSION_COOKIE, TOKEN),
                new Cookie(CustomsDeclarationProxyController.CSRF_COOKIE, "cookie-token"));
        request.addHeader(CustomsDeclarationProxyController.CSRF_HEADER, "forged-token");
        request.addHeader("Sec-Fetch-Site", "cross-site");
        MockHttpServletResponse response = new MockHttpServletResponse();

        controller.proxy(request, response);

        assertEquals(403, response.getStatus());
        assertTrue(response.getContentAsString().contains("请求来源校验失败"));
        verifyNoInteractions(proxyService);
    }

    @Test
    void postRejectsMismatchedForwardedOriginWithoutErrorDispatch() throws Exception
    {
        CustomsDeclarationProxyService proxyService = mock(CustomsDeclarationProxyService.class);
        CustomsDeclarationProxyController controller = new CustomsDeclarationProxyController(
                validSessions(), proxyService);
        MockHttpServletRequest request = new MockHttpServletRequest(
                "POST", CustomsDeclarationProxyController.PREFIX + "/api/export");
        request.setCookies(new Cookie(CustomsDeclarationProxyController.SESSION_COOKIE, TOKEN));
        request.addHeader("Origin", "https://evil.example.com");
        request.addHeader("X-Forwarded-Proto", "https");
        request.addHeader("X-Forwarded-Host", "erp.example.com");
        MockHttpServletResponse response = new MockHttpServletResponse();

        controller.proxy(request, response);

        assertEquals(403, response.getStatus());
        assertTrue(response.getContentAsString().contains("请求来源校验失败"));
        verifyNoInteractions(proxyService);
    }

    @Test
    void rewritesOnlyTheLegacyPageResourceAndApiRoots()
    {
        String html = "<script src=\"/static/app.js\"></script>";
        assertEquals("<script src=\"" + PUBLIC_BASE + "/static/app.js\"></script>",
                CustomsDeclarationProxyService.rewriteText(
                        "/index.html", html, PUBLIC_BASE));

        String js = "fetch('/api/search?q=x'); '<img src=\"/static/icon/jiahao.svg\">'";
        String rewritten = CustomsDeclarationProxyService.rewriteText(
                "/static/app.js", js, PUBLIC_BASE);
        assertTrue(rewritten.contains("fetch('" + PUBLIC_BASE + "/api/search?q=x')"));
        assertTrue(rewritten.contains("src=\"" + PUBLIC_BASE
                + "/static/icon/jiahao.svg\""));
    }

    @Test
    void upstreamUrlDropsOnlyInternalWorkbenchParameters()
    {
        CustomsDeclarationLegacyProperties properties =
                new CustomsDeclarationLegacyProperties();
        CustomsDeclarationProxyService service = new CustomsDeclarationProxyService(
                properties, mock(HttpClient.class));
        assertEquals("http://127.0.0.1:8010/customs-declaration/",
                service.buildTargetUrl("/index.html",
                        "erp_session=secret&api_base=%2Fprod-api%2Fsop%2Fcustoms-declaration%2Fproxy"));
        assertEquals("http://127.0.0.1:8010/customs-declaration/api/search?q=BMW-1",
                service.buildTargetUrl("/api/search", "q=BMW-1&erp_user_id=7"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void forwardsConfiguredInternalTokenToEmbeddedDateProject() throws Exception
    {
        CustomsDeclarationLegacyProperties properties =
                new CustomsDeclarationLegacyProperties();
        properties.setInternalToken("test-internal-token");
        HttpClient client = mock(HttpClient.class);
        when(client.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenAnswer(call -> {
                    HttpResponse<InputStream> result = mock(HttpResponse.class);
                    when(result.statusCode()).thenReturn(200);
                    when(result.headers()).thenReturn(
                            HttpHeaders.of(Map.of("Content-Type", List.of("text/html")),
                                    (name, value) -> true));
                    when(result.body()).thenReturn(new ByteArrayInputStream(
                            "<script src=\"/static/app.js\"></script>".getBytes()));
                    return result;
                });
        CustomsDeclarationProxyService service =
                new CustomsDeclarationProxyService(properties, client);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/index.html");
        MockHttpServletResponse response = new MockHttpServletResponse();
        ImageSopSessionService.SessionContext session =
                new ImageSopSessionService.SessionContext(
                        7L, "tester", Set.of(CustomsDeclarationProxyController.PERMISSION),
                        Instant.now().plusSeconds(3600));

        service.forward("/index.html", request, response, session, PUBLIC_BASE);

        assertEquals(200, response.getStatus());
        assertTrue(response.getContentAsString().contains(
                PUBLIC_BASE + "/static/app.js"));
        verify(client).send(argThat(upstream ->
                        upstream.uri().toString().equals(
                                "http://127.0.0.1:8010/customs-declaration/")
                                && upstream.headers().firstValue("X-Internal-Token")
                                        .orElse("").equals("test-internal-token")),
                any(HttpResponse.BodyHandler.class));
    }

    @Test
    @SuppressWarnings("unchecked")
    void forwardsExportJsonWithKnownContentLengthForEmbeddedWsgiApp() throws Exception
    {
        CustomsDeclarationLegacyProperties properties =
                new CustomsDeclarationLegacyProperties();
        HttpClient client = mock(HttpClient.class);
        when(client.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenAnswer(call -> {
                    HttpResponse<InputStream> result = mock(HttpResponse.class);
                    when(result.statusCode()).thenReturn(200);
                    when(result.headers()).thenReturn(
                            HttpHeaders.of(Map.of("Content-Type", List.of(
                                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                                    (name, value) -> true));
                    when(result.body()).thenReturn(new ByteArrayInputStream(
                            new byte[]{'P', 'K'}));
                    return result;
                });
        CustomsDeclarationProxyService service =
                new CustomsDeclarationProxyService(properties, client);
        byte[] json = "{\"items\":[{\"sku\":\"BMW-TEST\",\"quantity\":1}]}"
                .getBytes();
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/export");
        request.setContentType("application/json");
        request.setContent(json);
        MockHttpServletResponse response = new MockHttpServletResponse();
        ImageSopSessionService.SessionContext session =
                new ImageSopSessionService.SessionContext(
                        7L, "tester", Set.of(CustomsDeclarationProxyController.PERMISSION),
                        Instant.now().plusSeconds(3600));

        service.forward("/api/export", request, response, session, PUBLIC_BASE);

        assertEquals(200, response.getStatus());
        assertArrayEquals(new byte[]{'P', 'K'}, response.getContentAsByteArray());
        verify(client).send(argThat(upstream ->
                        upstream.uri().toString().endsWith("/api/export")
                                && upstream.headers().firstValue("Content-Type")
                                        .orElse("").equals("application/json")
                                && upstream.bodyPublisher().orElseThrow()
                                        .contentLength() == json.length),
                any(HttpResponse.BodyHandler.class));
    }

    @Test
    void publicBaseAndQueryParsingRejectAmbiguity()
    {
        assertEquals(PUBLIC_BASE,
                CustomsDeclarationProxyController.normalizePublicBase(PUBLIC_BASE + "/"));
        assertThrows(IllegalArgumentException.class,
                () -> CustomsDeclarationProxyController.normalizePublicBase(
                        "https://evil.example/sop/customs-declaration/proxy"));
        assertThrows(IllegalArgumentException.class,
                () -> CustomsDeclarationProxyController.query(
                        "erp_session=a&erp_session=b", "erp_session"));
    }
}
