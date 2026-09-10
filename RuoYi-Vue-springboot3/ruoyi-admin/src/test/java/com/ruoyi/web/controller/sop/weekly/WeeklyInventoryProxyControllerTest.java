package com.ruoyi.web.controller.sop.weekly;

import com.ruoyi.system.service.finance.PythonPerformanceTaskProperties;
import com.ruoyi.web.controller.sop.image.ImageSopSessionService;
import jakarta.servlet.http.Cookie;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class WeeklyInventoryProxyControllerTest
{
    private static final String TOKEN = "valid-weekly-session";

    private ImageSopSessionService validSessions()
    {
        ImageSopSessionService sessions = mock(ImageSopSessionService.class);
        when(sessions.validateAndTouch(TOKEN, WeeklyInventoryProxyController.PERMISSION))
            .thenReturn(new ImageSopSessionService.SessionContext(1L, "user",
                Set.of(WeeklyInventoryProxyController.PERMISSION), Instant.now().plusSeconds(3600)));
        return sessions;
    }

    @SuppressWarnings("unchecked")
    private HttpClient upstream() throws Exception
    {
        HttpClient client = mock(HttpClient.class);
        when(client.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class))).thenAnswer(call -> {
            HttpResponse<InputStream> result = mock(HttpResponse.class);
            when(result.statusCode()).thenReturn(200);
            when(result.headers()).thenReturn(HttpHeaders.of(Map.of(), (a,b) -> true));
            when(result.body()).thenReturn(new ByteArrayInputStream("ok".getBytes()));
            return result;
        });
        return client;
    }

    @Test void launchSetsScopedCookieAndRefreshWorksWithoutUrlToken() throws Exception
    {
        ImageSopSessionService sessions = validSessions();
        HttpClient client = upstream();
        WeeklyInventoryProxyController controller = new WeeklyInventoryProxyController(
            sessions, new PythonPerformanceTaskProperties(), client);
        MockHttpServletRequest launch = new MockHttpServletRequest("GET", WeeklyInventoryProxyController.PREFIX+"/index.html");
        launch.setQueryString("erp_session="+TOKEN);
        launch.addHeader("X-Forwarded-Proto", "https");
        MockHttpServletResponse first = new MockHttpServletResponse();
        controller.proxy(launch, first);
        assertEquals(200, first.getStatus());
        String cookie = first.getHeader("Set-Cookie");
        assertTrue(cookie.startsWith(WeeklyInventoryProxyController.SESSION_COOKIE+"="+TOKEN));
        assertTrue(cookie.contains("HttpOnly"));
        assertTrue(cookie.contains("SameSite=Strict"));
        assertTrue(cookie.contains("Secure"));
        assertFalse(cookie.contains("Path=")); // browser includes the nginx external prefix
        assertFalse(cookie.contains("Domain="));
        MockHttpServletRequest refresh = new MockHttpServletRequest("GET", WeeklyInventoryProxyController.PREFIX+"/index.html");
        refresh.setCookies(new Cookie(WeeklyInventoryProxyController.SESSION_COOKIE, TOKEN));
        MockHttpServletResponse second = new MockHttpServletResponse();
        controller.proxy(refresh, second);
        assertEquals(200, second.getStatus());
        verify(sessions, times(2)).validateAndTouch(TOKEN, WeeklyInventoryProxyController.PERMISSION);
        verify(client, times(2)).send(argThat(r -> r.uri().getRawQuery() == null), any(HttpResponse.BodyHandler.class));
    }

    @Test void invalidExplicitTokenCannotFallBackToValidCookie() throws Exception
    {
        HttpClient client = upstream();
        WeeklyInventoryProxyController controller = new WeeklyInventoryProxyController(validSessions(),new PythonPerformanceTaskProperties(),client);
        MockHttpServletRequest request = new MockHttpServletRequest("GET",WeeklyInventoryProxyController.PREFIX+"/index.html");
        request.setQueryString("erp_session=forged");
        request.setCookies(new Cookie(WeeklyInventoryProxyController.SESSION_COOKIE,TOKEN));
        MockHttpServletResponse response = new MockHttpServletResponse();
        controller.proxy(request,response);
        assertEquals(403,response.getStatus());
        assertNull(response.getHeader("Set-Cookie"));
        verifyNoInteractions(client);
    }

    @Test void expiredOrUnpermittedCookieIsRejected() throws Exception
    {
        HttpClient client = upstream();
        ImageSopSessionService sessions = mock(ImageSopSessionService.class);
        WeeklyInventoryProxyController controller = new WeeklyInventoryProxyController(sessions,new PythonPerformanceTaskProperties(),client);
        MockHttpServletRequest request = new MockHttpServletRequest("GET",WeeklyInventoryProxyController.PREFIX+"/files");
        request.setCookies(new Cookie(WeeklyInventoryProxyController.SESSION_COOKIE,"expired"));
        MockHttpServletResponse response = new MockHttpServletResponse();
        controller.proxy(request,response);
        assertEquals(403,response.getStatus());
        verify(sessions).validateAndTouch("expired",WeeklyInventoryProxyController.PERMISSION);
        verifyNoInteractions(client);
    }

    @Test void cookiePostRequiresSameOriginScriptMarker() throws Exception
    {
        HttpClient client = upstream();
        WeeklyInventoryProxyController controller = new WeeklyInventoryProxyController(validSessions(),new PythonPerformanceTaskProperties(),client);
        for (String site : new String[]{"cross-site","same-site","same-origin"})
        {
            MockHttpServletRequest request = new MockHttpServletRequest("POST",WeeklyInventoryProxyController.PREFIX+"/run");
            request.setCookies(new Cookie(WeeklyInventoryProxyController.SESSION_COOKIE,TOKEN));
            request.addHeader("X-Weekly-Request","1");
            request.addHeader("Sec-Fetch-Site",site);
            MockHttpServletResponse response = new MockHttpServletResponse();
            controller.proxy(request,response);
            assertEquals(site.equals("same-origin")?200:403,response.getStatus());
        }
        MockHttpServletRequest missing = new MockHttpServletRequest("POST",WeeklyInventoryProxyController.PREFIX+"/run");
        missing.setCookies(new Cookie(WeeklyInventoryProxyController.SESSION_COOKIE,TOKEN));
        MockHttpServletResponse response = new MockHttpServletResponse();
        controller.proxy(missing,response);
        assertEquals(403,response.getStatus());
        verify(client,times(1)).send(any(HttpRequest.class),any(HttpResponse.BodyHandler.class));
    }

    @Test void conflictingCookiesAreRejected() throws Exception
    {
        HttpClient client = upstream();
        WeeklyInventoryProxyController controller = new WeeklyInventoryProxyController(validSessions(),new PythonPerformanceTaskProperties(),client);
        MockHttpServletRequest request = new MockHttpServletRequest("GET",WeeklyInventoryProxyController.PREFIX+"/index.html");
        request.setCookies(new Cookie(WeeklyInventoryProxyController.SESSION_COOKIE,TOKEN),new Cookie(WeeklyInventoryProxyController.SESSION_COOKIE,"other"));
        MockHttpServletResponse response = new MockHttpServletResponse();
        controller.proxy(request,response);
        assertEquals(400,response.getStatus());
        verifyNoInteractions(client);
    }
    @Test void rejectsMissingAndForgedSessionsBeforeForwarding() throws Exception
    {
        ImageSopSessionService sessions=mock(ImageSopSessionService.class);
        WeeklyInventoryProxyController controller=new WeeklyInventoryProxyController(sessions,new PythonPerformanceTaskProperties());
        for(String token : new String[]{null,"forged"})
        {
            MockHttpServletRequest request=new MockHttpServletRequest("POST","/sop/weekly-inventory/proxy/run");
            if(token!=null)request.setQueryString("erp_session="+token);
            MockHttpServletResponse response=new MockHttpServletResponse();
            controller.proxy(request,response);
            assertEquals(403,response.getStatus());
            verify(sessions).validateAndTouch(token,"sop:weeklyInventory:use");
        }
    }
    @Test void strictMethodAndPathWhitelist()
    {
        assertTrue(WeeklyInventoryProxyController.allowed("GET","/files/1/download"));
        assertTrue(WeeklyInventoryProxyController.allowed("POST","/run"));
        assertFalse(WeeklyInventoryProxyController.allowed("GET","/run"));
        assertFalse(WeeklyInventoryProxyController.allowed("POST","/files"));
        assertFalse(WeeklyInventoryProxyController.allowed("GET","/files/../secret"));
        assertFalse(WeeklyInventoryProxyController.allowed("GET","/files/%2e%2e/download"));
    }
    @Test void onlyQueryStringIsParsed()
    {
        assertEquals("abc+123",WeeklyInventoryProxyController.query("api_base=x&erp_session=abc%2B123","erp_session"));
        assertThrows(IllegalArgumentException.class,()->WeeklyInventoryProxyController.query("erp_session=a&erp_session=b","erp_session"));
    }
}
