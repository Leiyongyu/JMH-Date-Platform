package com.ruoyi.system.service.finance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/** 用本机 HTTP 服务模拟 Python 调度接口，验证提交-轮询与旧版兼容路径。 */
class PythonPerformanceSchedulerClientPollTest
{
    private static final String COMPLETED =
            "{\"code\":0,\"data\":{\"run_id\":\"r1\",\"status\":\"completed\",\"result\":{\"extract_rows\":3}}}";

    private HttpServer server;
    private final List<String> calls = new CopyOnWriteArrayList<>();

    @AfterEach
    void stop()
    {
        if (server != null) server.stop(0);
    }

    private PythonPerformanceSchedulerClient client(Map<String, Handler> routes) throws IOException
    {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            String key = exchange.getRequestMethod() + " " + exchange.getRequestURI().getPath();
            calls.add(key);
            Handler handler = routes.get(key);
            if (handler == null) respond(exchange, 404, "{\"detail\":\"Not Found\"}");
            else handler.handle(exchange);
        });
        server.start();
        PythonPerformanceTaskProperties properties = new PythonPerformanceTaskProperties();
        properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
        properties.setReadTimeout(Duration.ofSeconds(10));
        properties.setPollInterval(Duration.ofMillis(10));
        properties.setInternalToken("t");
        return new PythonPerformanceSchedulerClient(properties, new ObjectMapper());
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException
    {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    interface Handler
    {
        void handle(HttpExchange exchange) throws IOException;
    }

    @Test
    void submitsThenPollsUntilCompleted() throws Exception
    {
        AtomicInteger polls = new AtomicInteger();
        PythonPerformanceSchedulerClient client = client(Map.of(
                "POST /api/v1/internal/scheduler/tasks/currency_month_sync/runs",
                exchange -> respond(exchange, 202, "{\"code\":0,\"data\":{\"run_id\":\"r1\",\"status\":\"running\"}}"),
                "GET /api/v1/internal/scheduler/runs/r1",
                exchange -> {
                    if (polls.incrementAndGet() < 3)
                        respond(exchange, 202, "{\"code\":0,\"data\":{\"status\":\"running\"}}");
                    else
                        respond(exchange, 200, COMPLETED);
                }));

        Map<String, Object> json = client.runCurrencyMonth("2026-09", "req-1");

        assertEquals(3, polls.get());
        assertEquals("completed", ((Map<?, ?>) json.get("data")).get("status"));
        assertTrue(calls.stream().noneMatch(call -> call.endsWith("/run")), calls.toString());
    }

    @Test
    void fallsBackToSynchronousEndpointOnOldPython() throws Exception
    {
        PythonPerformanceSchedulerClient client = client(Map.of(
                "POST /api/v1/internal/scheduler/tasks/currency_month_sync/run",
                exchange -> respond(exchange, 201, COMPLETED)));

        Map<String, Object> json = client.runCurrencyMonth("2026-09", "req-1");

        assertEquals(0, ((Number) json.get("code")).intValue());
        assertEquals(List.of(
                "POST /api/v1/internal/scheduler/tasks/currency_month_sync/runs",
                "POST /api/v1/internal/scheduler/tasks/currency_month_sync/run"), calls);
    }

    @Test
    void pollFailureSurfacesPythonError() throws Exception
    {
        PythonPerformanceSchedulerClient client = client(Map.of(
                "POST /api/v1/internal/scheduler/tasks/currency_month_sync/runs",
                exchange -> respond(exchange, 202, "{\"code\":0,\"data\":{\"run_id\":\"r1\"}}"),
                "GET /api/v1/internal/scheduler/runs/r1",
                exchange -> respond(exchange, 502, "{\"detail\":\"内部任务执行失败: 领星超时\"}")));

        IllegalStateException error = assertThrows(IllegalStateException.class,
                () -> client.runCurrencyMonth("2026-09", "req-1"));
        assertTrue(error.getMessage().contains("领星超时"), error.getMessage());
    }
}
