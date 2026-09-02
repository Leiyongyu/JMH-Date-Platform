package com.ruoyi.system.service.operation.external.goodcang;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class GoodcangClientTest
{
    private HttpServer server;

    @AfterEach
    void stopServer()
    {
        if (server != null) server.stop(0);
    }

    @Test
    void retriesHttp429UntilRequestSucceeds() throws Exception
    {
        AtomicInteger calls = new AtomicInteger();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/inventory/inventory_age_list", exchange -> {
            int call = calls.incrementAndGet();
            boolean limited = call <= 2;
            byte[] body = (limited
                    ? "{\"code\":429,\"message\":\"访问过快\"}"
                    : "{\"code\":0,\"message\":\"Success\",\"data\":{\"total\":1,\"list\":[{}]}}")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(limited ? 429 : 200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();

        GoodcangProperties properties = new GoodcangProperties();
        properties.setEndpoint("http://127.0.0.1:" + server.getAddress().getPort());
        properties.setAppToken("test-token");
        properties.setAppKey("test-key");
        properties.setMinRequestIntervalMs(0L);
        properties.setMaxRateLimitRetries(2);
        properties.setRateLimitInitialBackoffMs(1L);
        properties.setRateLimitMaxBackoffMs(2L);

        GoodcangClient client = new GoodcangClient(properties, new ObjectMapper());
        Map<String, Object> response = client.getInventoryAgeList(1, 200);

        assertThat(response.get("code")).isEqualTo(0);
        assertThat(calls.get()).isEqualTo(3);
    }
}
