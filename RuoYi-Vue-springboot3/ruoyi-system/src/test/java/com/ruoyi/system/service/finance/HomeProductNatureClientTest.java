package com.ruoyi.system.service.finance;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class HomeProductNatureClientTest
{
    @Test void ownerQueryForwardsSegmentAndBatchButNotArbitraryParameters() throws Exception
    {
        var received = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            received.set(exchange.getRequestURI().toString());
            byte[] body = "{\"code\":0,\"data\":{\"items\":[]}}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try
        {
            var properties = new PerformancePythonProperties();
            properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
            var client = new PerformancePythonClient(properties, new ObjectMapper());
            for (String platform : java.util.List.of("amz", "ebay"))
            {
                client.productNature(platform, "owners", Map.of("month", "2026-09", "segment_key", "德国",
                    "batch_id", "00000000-0000-0000-0000-000000000000", "url", "not-allowed"), "trace");
                String uri = URLDecoder.decode(received.get(), StandardCharsets.UTF_8);
                assertTrue(uri.startsWith("/" + platform + "-owner-sku/nature/owners?"));
                assertTrue(uri.contains("segment_key=德国"));
                assertTrue(uri.contains("batch_id=00000000-0000-0000-0000-000000000000"));
                assertTrue(uri.contains("month=2026-09"));
                assertFalse(uri.contains("not-allowed"));
            }
            assertThrows(IllegalArgumentException.class, () -> client.productNature("amz", "../evil", Map.of(), "trace"));
        }
        finally { server.stop(0); }
    }
}
