package com.ruoyi.system.service.operation.ebay;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import static org.junit.jupiter.api.Assertions.*;

/** Only connects to an ephemeral local stub; never contacts Python or a business API. */
class EbayInventoryDetailPythonClientTest
{
    private HttpServer server;
    private EbayInventoryDetailPythonClient client;
    private String receivedMethod;
    private String receivedPath;
    private String receivedQuery;
    private String receivedToken;
    private String receivedRequestId;
    private String receivedAccept;
    private String receivedContentType;
    private byte[] receivedBody;
    private int responseStatus = 200;
    private String responseType = "application/json";
    private String responseDisposition;
    private byte[] responseBody = "{\"code\":0,\"data\":{\"items\":[],\"total\":3}}"
            .getBytes(StandardCharsets.UTF_8);

    @BeforeEach
    void createLocalStub() throws Exception
    {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            receivedMethod = exchange.getRequestMethod();
            receivedPath = exchange.getRequestURI().getPath();
            receivedQuery = exchange.getRequestURI().getRawQuery();
            receivedToken = exchange.getRequestHeaders().getFirst("X-Internal-Token");
            receivedRequestId = exchange.getRequestHeaders().getFirst("X-Request-ID");
            receivedAccept = exchange.getRequestHeaders().getFirst("Accept");
            receivedContentType = exchange.getRequestHeaders().getFirst("Content-Type");
            receivedBody = exchange.getRequestBody().readAllBytes();
            exchange.getResponseHeaders().set("Content-Type", responseType);
            if (responseDisposition != null)
                exchange.getResponseHeaders().set("Content-Disposition", responseDisposition);
            exchange.sendResponseHeaders(responseStatus, responseBody.length);
            exchange.getResponseBody().write(responseBody);
            exchange.close();
        });
        server.start();
        var properties = new PerformancePythonProperties();
        properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort() + "/api/v1/finance");
        properties.setInternalToken("test-only-internal-token");
        client = new EbayInventoryDetailPythonClient(properties, new ObjectMapper());
    }

    @AfterEach
    void stopLocalStub()
    {
        server.stop(0);
    }

    @Test
    void priceImportUsesMultipartAuthenticatedOperatorAndExistingInternalHeaders()
    {
        responseBody = ("{\"code\":0,\"data\":{\"imported_rows\":3,\"duplicate_rows\":2,"
                + "\"sku_count\":2,\"middle_code_count\":1,\"skipped_rows\":0,\"warnings\":[]}}")
                .getBytes(StandardCharsets.UTF_8);
        var file = new MockMultipartFile("file", "产品单价明细表.xlsx",
                EbayInventoryDetailPythonClient.EXCEL_CONTENT_TYPE, "PK-price-payload".getBytes(StandardCharsets.UTF_8));

        var result = client.importPrices(file, "李 茫茫", " price-import-request ");

        assertEquals("POST", receivedMethod);
        assertEquals("/api/v1/finance/ebay-inventory-detail/prices/import", receivedPath);
        assertEquals(Map.of("operator", "李 茫茫"), query());
        assertEquals("test-only-internal-token", receivedToken);
        assertEquals("price-import-request", receivedRequestId);
        assertTrue(receivedContentType.startsWith("multipart/form-data; boundary="));
        String body = new String(receivedBody, StandardCharsets.UTF_8);
        assertTrue(body.contains("name=\"file\""));
        assertTrue(body.contains("filename=\"产品单价明细表.xlsx\""));
        assertTrue(body.contains("PK-price-payload"));
        assertEquals(3, ((Map<?, ?>) result.get("data")).get("imported_rows"));
    }

    @Test
    void historyUploadHasSeparate50MbLimitAndRetainsBody()
    {
        var content = new byte[11 * 1024 * 1024];
        content[0] = 80;
        var file = new MockMultipartFile("file", "history.xlsx", "application/octet-stream", content);
        assertThrows(IllegalArgumentException.class, () -> client.importPrices(file, "operator", null));
        client.importHistory(file, "operator", "history-request");
        assertEquals("/api/v1/finance/ebay-inventory-detail/history/import", receivedPath);
        assertEquals("POST", receivedMethod);
        assertEquals("history-request", receivedRequestId);
        assertTrue(receivedBody.length > content.length);
        assertEquals("test-only-internal-token", receivedToken);
    }

    @Test
    void priceImportRejectsMissingEmptyAndOversizedFilesBeforeCallingPython()
    {
        assertThrows(IllegalArgumentException.class, () -> client.importPrices(null, "user", null));
        var empty = new MockMultipartFile("file", new byte[0]);
        assertThrows(IllegalArgumentException.class, () -> client.importPrices(empty, "user", null));
        var oversized = new MockMultipartFile("file", new byte[] { 80 })
        {
            @Override public long getSize() { return 10L * 1024 * 1024 + 1; }
        };
        var error = assertThrows(IllegalArgumentException.class,
                () -> client.importPrices(oversized, "user", null));
        assertTrue(error.getMessage().contains("产品单价文件不能超过10MB"));
        assertNull(receivedMethod);
    }

    @Test
    void priceImportPreservesServerValidationErrorAndPostsOperator()
    {
        var file = new MockMultipartFile("file", "prices.xlsx", "application/octet-stream", new byte[] { 80, 75 });
        responseStatus = 400;
        responseBody = "{\"detail\":\"第 3 行单价无效，未更新任何记录\"}".getBytes(StandardCharsets.UTF_8);
        var error = assertThrows(IllegalStateException.class, () -> client.importPrices(file, "user", null));
        assertTrue(error.getMessage().contains("第 3 行单价无效，未更新任何记录"));

        responseStatus = 200;
        responseBody = "{\"code\":0,\"data\":{\"imported_rows\":1}}".getBytes(StandardCharsets.UTF_8);
        client.importPrices(file, "price-user", "price-trace");
        assertEquals("/api/v1/finance/ebay-inventory-detail/prices/import", receivedPath);
        assertEquals("price-user", query().get("operator"));
    }

    @Test
    void recalculatePostsWithoutClientDateFiltersOrBodyAndPreservesInternalHeaders()
    {
        responseBody = "{\"code\":0,\"data\":{\"stat_date\":\"2026-09-16\",\"row_count\":37}}"
                .getBytes(StandardCharsets.UTF_8);
        Map<String, Object> result = client.recalculateSnapshot(" recalculate-request ");

        assertEquals("POST", receivedMethod);
        assertEquals("/api/v1/finance/ebay-inventory-detail/snapshot/recalculate", receivedPath);
        assertNull(receivedQuery);
        assertEquals(0, receivedBody.length);
        assertEquals("test-only-internal-token", receivedToken);
        assertEquals("recalculate-request", receivedRequestId);
        assertEquals("application/json", receivedAccept);
        assertEquals(0, result.get("code"));
        assertEquals(Map.of("stat_date", "2026-09-16", "row_count", 37), result.get("data"));
    }

    @Test
    void recalculateRejectsPythonBusinessErrors()
    {
        responseBody = "{\"code\":1,\"message\":\"今日快照重算失败\"}".getBytes(StandardCharsets.UTF_8);
        var error = assertThrows(IllegalStateException.class, () -> client.recalculateSnapshot(null));
        assertTrue(error.getMessage().contains("今日快照重算失败"));
        assertNotNull(receivedRequestId);
    }

    @Test
    void pivotUsesGetAndEncodesFiltersWithExistingInternalHeaders()
    {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("start_date", "2026-09-01");
        params.put("end_date", "2026-09-16");
        params.put("owner", "李 茫茫");
        params.put("site", "德国");
        params.put("page", 2);
        params.put("page_size", 50);
        params.put("sort_field", "stat_date");
        params.put("sort_order", "descending");
        params.put("unused", null);
        Map<String, Object> result = client.pivot(params, " pivot-request ");
        assertEquals("GET", receivedMethod);
        assertEquals("/api/v1/finance/ebay-inventory-detail/pivot", receivedPath);
        assertEquals("test-only-internal-token", receivedToken);
        assertEquals("pivot-request", receivedRequestId);
        assertEquals("application/json", receivedAccept);
        assertEquals(0, receivedBody.length);
        Map<String, String> query = query();
        assertEquals("李 茫茫", query.get("owner"));
        assertEquals("德国", query.get("site"));
        assertEquals("2026-09-01", query.get("start_date"));
        assertEquals("2026-09-16", query.get("end_date"));
        assertEquals("2", query.get("page"));
        assertEquals("50", query.get("page_size"));
        assertEquals("stat_date", query.get("sort_field"));
        assertEquals("descending", query.get("sort_order"));
        assertFalse(query.containsKey("unused"));
        assertEquals(3, ((Map<?, ?>) result.get("data")).get("total"));
    }

    @Test
    void pivotExportPreservesExcelBytesAndUtf8Filename()
    {
        responseType = EbayInventoryDetailPythonClient.EXCEL_CONTENT_TYPE;
        responseBody = new byte[] { 80, 75, 3, 4, 0, -1, 127 };
        responseDisposition = "attachment; filename=pivot.xlsx; filename*=UTF-8''%E5%BA%93%E5%AD%98.xlsx";
        var result = client.exportPivot(Map.of("owner", "负责人", "site", "英国"), "export-request");
        assertEquals("GET", receivedMethod);
        assertEquals("/api/v1/finance/ebay-inventory-detail/pivot/export", receivedPath);
        assertEquals("负责人", query().get("owner"));
        assertEquals("英国", query().get("site"));
        assertEquals("export-request", receivedRequestId);
        assertEquals("test-only-internal-token", receivedToken);
        assertEquals(EbayInventoryDetailPythonClient.EXCEL_CONTENT_TYPE, receivedAccept);
        assertArrayEquals(responseBody, result.content());
        assertEquals(responseDisposition, result.contentDisposition());
    }

    @Test
    void pivotExportGeneratesSafeFilenameWhenDispositionIsMissing()
    {
        responseType = EbayInventoryDetailPythonClient.EXCEL_CONTENT_TYPE;
        var result = client.exportPivot(Map.of(), null);
        assertTrue(result.contentDisposition().startsWith("attachment; filename=ebay-inventory-pivot.xlsx;"));
        assertTrue(result.contentDisposition().contains("filename*=UTF-8''"));
        assertFalse(result.contentDisposition().contains("\r"));
        assertFalse(result.contentDisposition().contains("\n"));
        assertNotNull(receivedRequestId);
    }

    @Test
    void pivotRejectsPythonValidationError()
    {
        responseStatus = 400;
        responseBody = "{\"detail\":\"开始日期不能晚于结束日期\"}".getBytes(StandardCharsets.UTF_8);
        var error = assertThrows(IllegalStateException.class, () -> client.pivot(Map.of(), "invalid-range"));
        assertTrue(error.getMessage().contains("HTTP 400"));
        assertTrue(error.getMessage().contains("开始日期不能晚于结束日期"));
    }

    @Test
    void pivotExportRejectsJsonResponseEvenWithHttp200()
    {
        responseBody = "{\"detail\":\"没有符合条件的历史记录\"}".getBytes(StandardCharsets.UTF_8);
        var error = assertThrows(IllegalStateException.class, () -> client.exportPivot(Map.of(), "empty-export"));
        assertTrue(error.getMessage().contains("没有符合条件的历史记录"));
    }

    @Test
    void pivotExportRejectsUnexpectedContentType()
    {
        responseType = "text/html";
        assertThrows(IllegalStateException.class, () -> client.exportPivot(Map.of(), "not-excel"));
    }

    @Test
    void originalDetailExportStillPostsJsonAndForwardsBinary() throws Exception
    {
        responseType = EbayInventoryDetailPythonClient.EXCEL_CONTENT_TYPE;
        responseBody = new byte[] { 80, 75, 0, -1 };
        Map<String, Object> payload = Map.of("site", "德国", "selected_keys", java.util.List.of("德国|SKU"));
        var result = client.export(payload, "original-export");
        assertEquals("POST", receivedMethod);
        assertEquals("/api/v1/finance/ebay-inventory-detail/export", receivedPath);
        assertEquals(payload, new ObjectMapper().readValue(receivedBody, Map.class));
        assertArrayEquals(responseBody, result.content());
        assertTrue(result.contentDisposition().contains("filename=ebay-inventory-detail.xlsx;"));
    }

    private Map<String, String> query()
    {
        return Arrays.stream(receivedQuery.split("&")).map(part -> part.split("=", 2))
                .collect(Collectors.toMap(pair -> decode(pair[0]), pair -> decode(pair[1])));
    }

    private static String decode(String value)
    {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }
}
