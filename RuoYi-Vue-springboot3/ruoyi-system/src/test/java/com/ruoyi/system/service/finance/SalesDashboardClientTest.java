package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import static org.junit.jupiter.api.Assertions.*;

class SalesDashboardClientTest
{
    @Test void forwardsQueryAndMultipartToInternalApi() throws Exception
    {
        var uri = new AtomicReference<String>();
        var body = new AtomicReference<String>();
        var contentType = new AtomicReference<String>();
        var token = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            uri.set(URLDecoder.decode(exchange.getRequestURI().toString(), StandardCharsets.UTF_8));
            body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            contentType.set(exchange.getRequestHeaders().getFirst("Content-Type"));
            token.set(exchange.getRequestHeaders().getFirst("X-Internal-Token"));
            var response = "{\"code\":0,\"data\":{\"row_count\":65}}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response); exchange.close();
        });
        server.start();
        try
        {
            var config = new PerformancePythonProperties();
            config.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort() + "/api/v1/finance");
            config.setInternalToken("test-only-token");
            var client = new PerformancePythonClient(config, new ObjectMapper());
            client.salesDashboardReport(Map.of("platform", "ebay", "start_month", "2026-01",
                    "end_month", "2026-09", "groups_csv", "DE,US"), "trace");
            assertTrue(uri.get().startsWith("/api/v1/finance/sales-dashboard/report?"));
            assertTrue(uri.get().contains("groups_csv=DE,US"));
            assertEquals("test-only-token", token.get());
            var file = new MockMultipartFile("file", "history.xlsx", "application/octet-stream", "sample-bytes".getBytes(StandardCharsets.UTF_8));
            client.importSalesHistory(file, "digest", "actual-user", "trace");
            assertTrue(uri.get().startsWith("/api/v1/finance/sales-dashboard/import?"));
            assertTrue(uri.get().contains("file_sha256=digest"));
            assertTrue(uri.get().contains("operator=actual-user"));
            assertTrue(contentType.get().startsWith("multipart/form-data; boundary="));
            assertTrue(body.get().contains("name=\"file\""));
            assertTrue(body.get().contains("sample-bytes"));
        }
        finally { server.stop(0); }
    }
}
