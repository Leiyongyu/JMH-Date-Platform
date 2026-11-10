package com.ruoyi.web.controller.operation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.common.constant.Constants;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.service.finance.PerformancePythonProperties;
import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.ebay.EbayPriceAnalysisPythonClient;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import com.ruoyi.web.task.PythonEbayStoreListingSyncTask;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 只验证转发、权限与定时任务编排；不连 Python，不连库。 */
class EbayPriceAnalysisControllerTest
{
    private static final String EXCEL_TYPE =
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    @AfterEach
    void clear()
    {
        SecurityContextHolder.clearContext();
        OperationSyncContext.clear();
    }

    @Test
    void overviewForwardsSnakeCaseFiltersAndUnwrapsData() throws Exception
    {
        var client = mock(EbayPriceAnalysisPythonClient.class);
        when(client.overview(any(), eq("trace"))).thenReturn(Map.of("code", 0,
                "data", Map.of("stat_date", "2026-09-23",
                        "kpis", List.of(Map.of("key", "listing_count", "value", 18013)))));
        var mvc = MockMvcBuilders.standaloneSetup(
                new EbayPriceAnalysisController(client)).build();

        mvc.perform(get("/operations/ebay/price-analysis/overview")
                        .param("statDate", "2026-09-23")
                        .param("sites", "DE,UK")
                        .param("accounts", " aplus-shop ")
                        .param("status", "超卖风险")
                        .param("keyword", "TYT-90245")
                        .param("dimension", "mid")
                        .header("X-Request-ID", "trace"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.stat_date").value("2026-09-23"))
                .andExpect(jsonPath("$.data.kpis[0].value").value(18013));

        Map<String, ?> params = captureParams(client, true);
        assertEquals("2026-09-23", params.get("stat_date"));
        assertEquals("DE,UK", params.get("sites"));
        assertEquals("aplus-shop", params.get("accounts"));
        assertEquals("超卖风险", params.get("status"));
        assertEquals("TYT-90245", params.get("keyword"));
        assertEquals("mid", params.get("dimension"));
    }

    @Test
    void detailClampsPagingAndBlankFiltersBecomeNull() throws Exception
    {
        var client = mock(EbayPriceAnalysisPythonClient.class);
        when(client.detail(any(), any())).thenReturn(Map.of("code", 0,
                "data", Map.of("total", 18013, "rows", List.of())));
        var mvc = MockMvcBuilders.standaloneSetup(
                new EbayPriceAnalysisController(client)).build();

        mvc.perform(get("/operations/ebay/price-analysis/detail")
                        .param("mode", "summary")
                        .param("pageNum", "0")
                        .param("pageSize", "5000")
                        .param("sortBy", "stock_gap")
                        .param("sortOrder", "desc")
                        .param("sites", "   "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(18013));

        Map<String, ?> params = captureParams(client, false);
        assertEquals("summary", params.get("mode"));
        assertEquals(1, params.get("page"));
        assertEquals(200, params.get("page_size"));
        assertEquals("stock_gap", params.get("sort_by"));
        assertEquals("desc", params.get("sort_order"));
        assertNull(params.get("sites"));
        assertTrue(params.containsKey("sites"));
    }

    @Test
    void exportSendsOnlyPermittedColumnsInFixedOrderAndStreamsWorkbook() throws Exception
    {
        var client = mock(EbayPriceAnalysisPythonClient.class);
        byte[] workbook = new byte[] { 80, 75, 3, 4 };
        when(client.export(any(), any())).thenReturn(
                new EbayPriceAnalysisPythonClient.ExcelFile(workbook,
                        "attachment; filename=ebay-price-analysis.xlsx"));
        // 故意乱序给权限：导出列顺序必须由后端的固定顺序决定，不受权限集合顺序影响。
        login(Set.of("operations:ebayPriceAnalysis:exportColumn:status",
                "operations:ebayPriceAnalysis:exportColumn:sku",
                "operations:ebayPriceAnalysis:exportColumn:seller_account"));
        var response = new MockHttpServletResponse();

        new EbayPriceAnalysisController(client).exportByGet("2026-09-23", "US", null,
                null, null, "detail", "stock_gap", "asc", "trace", response);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, ?>> captor = ArgumentCaptor.forClass(Map.class);
        verify(client).export(captor.capture(), eq("trace"));
        assertEquals("seller_account,sku,status", captor.getValue().get("columns"));
        assertEquals("2026-09-23", captor.getValue().get("stat_date"));
        assertEquals("US", captor.getValue().get("sites"));
        assertFalse(captor.getValue().containsKey("page"));
        assertFalse(captor.getValue().containsKey("page_size"));
        assertEquals(EXCEL_TYPE, response.getContentType());
        assertEquals("attachment; filename=ebay-price-analysis.xlsx",
                response.getHeader("Content-Disposition"));
        assertEquals("Content-Disposition",
                response.getHeader("Access-Control-Expose-Headers"));
        assertEquals("no-store", response.getHeader("Cache-Control"));
        assertArrayEquals(workbook, response.getContentAsByteArray());
    }

    @Test
    void exportRefusesUserWithoutAnyColumnPermissionBeforeCallingPython()
    {
        var client = mock(EbayPriceAnalysisPythonClient.class);
        login(Set.of("operations:ebayPriceAnalysis:list",
                "operations:ebayPriceAnalysis:export"));

        var error = assertThrows(ServiceException.class,
                () -> new EbayPriceAnalysisController(client).exportByPost(null, null, null,
                        null, null, "detail", null, null, null,
                        new MockHttpServletResponse()));

        assertEquals(Integer.valueOf(403), error.getCode());
        assertTrue(error.getMessage().contains("导出字段权限"));
        verifyNoInteractions(client);
    }

    @Test
    void builtInAllPermissionExportsEveryColumn() throws Exception
    {
        var client = mock(EbayPriceAnalysisPythonClient.class);
        when(client.export(any(), any())).thenReturn(
                new EbayPriceAnalysisPythonClient.ExcelFile(new byte[] { 80, 75 },
                        "attachment; filename=all.xlsx"));
        login(Set.of(Constants.ALL_PERMISSION));

        new EbayPriceAnalysisController(client).exportByPost(null, null, null, null, null,
                "summary", null, null, null, new MockHttpServletResponse());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, ?>> captor = ArgumentCaptor.forClass(Map.class);
        verify(client).export(captor.capture(), any());
        String columns = String.valueOf(captor.getValue().get("columns"));
        assertEquals(19, columns.split(",").length);
        assertTrue(columns.startsWith("seller_account,site_name,sku,title,currency,"));
        assertTrue(columns.endsWith("purchase_cost_cny,status,view_item_url"));
    }

    @Test
    void everyRouteIsGuardedByItsOwnPermission()
    {
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("u", "x", List.of()));
            var controller = context.getBean(EbayPriceAnalysisController.class);
            var client = context.getBean(EbayPriceAnalysisPythonClient.class);
            var perms = context.getBean(Permissions.class);

            assertThrows(AccessDeniedException.class,
                    () -> controller.overview(null, null, null, null, null, "sku", null));
            // 有查看权限不等于能导出。
            perms.allowed = Set.of("operations:ebayPriceAnalysis:list");
            assertThrows(AccessDeniedException.class,
                    () -> controller.exportByGet(null, null, null, null, null, "detail",
                            null, null, null, new MockHttpServletResponse()));
            verifyNoInteractions(client);

            when(client.overview(any(), any())).thenReturn(
                    Map.of("code", 0, "data", Map.of("stat_date", "2026-09-23")));
            assertNotNull(controller.overview(null, null, null, null, null, "sku", null)
                    .get("data"));
        }
    }

    @Test
    void weeklyTaskTreatsEmptySnapshotAsFailureAndNeverRefreshes()
    {
        var fixture = new TaskFixture();
        when(fixture.scheduler.runEbayStoreListing(anyString())).thenReturn(response(0, 0, 0));

        var error = assertThrows(IllegalStateException.class, fixture.task::runWeekly);

        assertTrue(error.getMessage().contains("eBay在售刊登每周同步失败"));
        assertTrue(error.getCause().getMessage().contains("空快照"));
        // listing 失败：不拉谷仓，也不刷表。
        verify(fixture.scheduler, never()).runGoodcangProductInventory(anyString());
        verify(fixture.scheduler, never()).runEbayPriceAnalysisRefresh(anyString());
        var result = captureFinish(fixture);
        assertEquals(OperationSyncResult.STATUS_FAILED, result.getStatus());
    }

    @Test
    void weeklyTaskKeepsSuccessfulListingPullWhenRefreshFails()
    {
        var fixture = new TaskFixture();
        when(fixture.scheduler.runEbayStoreListing(anyString()))
                .thenReturn(response(18013, 18013, 37));
        when(fixture.scheduler.runEbayPriceAnalysisRefresh(anyString()))
                .thenThrow(new IllegalStateException("Python绩效ETL错误[HTTP 502]: 内部任务执行失败: boom"));

        fixture.task.runWeekly();

        var result = captureFinish(fixture);
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertEquals(18013, result.getSuccessCount());
        assertTrue(result.getBusinessSummary().contains("店铺数=37"));
        assertTrue(result.getBusinessSummary().contains("刷表失败"));
        // 非锁冲突的失败不重试
        verify(fixture.scheduler, times(1)).runEbayPriceAnalysisRefresh(anyString());
        // 刷表失败必须单独告警，否则看板会悄悄停在上一次快照。
        verify(fixture.alerts).sendAlert(eq("ebay"),
                eq("ebay_price_analysis_weekly_sync:refresh"), anyString(), anyString(),
                eq("FAILED"), contains("HTTP 502"), isNull());
    }

    @Test
    void weeklyTaskRunsListingThenGoodcangThenRefresh()
    {
        var fixture = new TaskFixture();
        when(fixture.scheduler.runEbayStoreListing(anyString()))
                .thenReturn(response(18013, 18013, 37));
        when(fixture.scheduler.runEbayPriceAnalysisRefresh(anyString())).thenReturn(Map.of("code", 0,
                "data", Map.of("status", "completed", "result",
                        Map.of("rows", 18013, "matched_rows", 16566, "stat_date", "2026-11-10"))));

        fixture.task.runWeekly();

        var order = inOrder(fixture.scheduler);
        order.verify(fixture.scheduler).runEbayStoreListing(anyString());
        order.verify(fixture.scheduler).runGoodcangProductInventory(anyString());
        order.verify(fixture.scheduler).runEbayPriceAnalysisRefresh(anyString());
        var result = captureFinish(fixture);
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("价格分析刷表成功：DWS行数=18013"),
                result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("未匹配库存=1447"), result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("谷仓库存同步成功：写入=9120"),
                result.getBusinessSummary());
        verify(fixture.alerts, never()).sendAlert(anyString(), anyString(), anyString(), anyString(),
                anyString(), anyString(), any());
    }

    @Test
    void listingOnlyRunPullsWithoutTouchingPriceAnalysis()
    {
        var fixture = new TaskFixture();
        when(fixture.scheduler.runEbayStoreListing(anyString()))
                .thenReturn(response(18013, 18013, 37));

        fixture.task.syncListingOnly();

        verify(fixture.scheduler).runEbayStoreListing(anyString());
        verify(fixture.scheduler, never()).runGoodcangProductInventory(anyString());
        verify(fixture.scheduler, never()).runEbayPriceAnalysisRefresh(anyString());
        verifyNoInteractions(fixture.priceAnalysis);
        var result = captureFinish(fixture);
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("未执行价格分析刷表"));
    }

    @Test
    void weeklyTaskRejectsResponseFromAnOutdatedPythonService()
    {
        var fixture = new TaskFixture();
        when(fixture.scheduler.runEbayStoreListing(anyString()))
                .thenReturn(Map.of("code", 0, "data", Map.of("status", "completed")));

        var error = assertThrows(IllegalStateException.class, fixture.task::runWeekly);

        assertTrue(error.getCause().getMessage().contains("最新Python服务"));
        verify(fixture.scheduler, never()).runEbayPriceAnalysisRefresh(anyString());
    }

    /**
     * 锁住与 Python 的路径契约：设计文档第 4 节的 router 挂在 /api/v1/ebay-price-analysis，
     * 不在 /finance 下，而共用配置的 base-url 带 /finance 后缀。
     * 只连本机临时 stub，不碰真的 Python。
     */
    @Test
    void clientCallsContractPathsWithInternalTokenAndRequestId() throws Exception
    {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        String[] seen = new String[4];
        server.createContext("/", exchange -> {
            seen[0] = exchange.getRequestURI().getPath();
            seen[1] = exchange.getRequestURI().getRawQuery();
            seen[2] = exchange.getRequestHeaders().getFirst("X-Internal-Token");
            seen[3] = exchange.getRequestHeaders().getFirst("X-Request-ID");
            boolean excel = seen[0].endsWith("/export");
            byte[] body = excel ? new byte[] { 80, 75, 3, 4 }
                    : "{\"code\":0,\"data\":{\"status\":\"accepted\"}}"
                            .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type",
                    excel ? EXCEL_TYPE : "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try
        {
            var properties = new PerformancePythonProperties();
            properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort()
                    + "/api/v1/finance");
            properties.setInternalToken("test-only-internal-token");
            var client = new EbayPriceAnalysisPythonClient(properties, new ObjectMapper());

            client.overview(Map.of("sites", "DE"), "trace");
            assertEquals("/api/v1/ebay-price-analysis/overview", seen[0]);
            assertEquals("sites=DE", seen[1]);
            assertEquals("test-only-internal-token", seen[2]);
            assertEquals("trace", seen[3]);

            client.detail(Map.of("page", 2), "trace");
            assertEquals("/api/v1/ebay-price-analysis/detail", seen[0]);

            var file = client.export(Map.of("columns", "sku,status"), "trace");
            assertEquals("/api/v1/ebay-price-analysis/export", seen[0]);
            assertEquals("columns=sku%2Cstatus", seen[1]);
            // Python 没给 Content-Disposition 时后端兜一个安全的文件名。
            assertTrue(file.contentDisposition().startsWith(
                    "attachment; filename=ebay-price-analysis.xlsx;"));

        }
        finally
        {
            server.stop(0);
        }
    }

    private static Map<String, Object> response(int extract, int ods, int shops)
    {
        return Map.of("code", 0, "data", Map.of("status", "completed",
                "result", Map.of("extract_rows", extract, "ods_rows", ods,
                        "shop_count", shops, "sync_batch_id", "batch-1")));
    }

    private static OperationSyncResult captureFinish(TaskFixture fixture)
    {
        var captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(fixture.logs).finish(eq(77L), captor.capture());
        return captor.getValue();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, ?> captureParams(
            EbayPriceAnalysisPythonClient client, boolean overview)
    {
        ArgumentCaptor<Map<String, ?>> captor = ArgumentCaptor.forClass(Map.class);
        if (overview) verify(client).overview(captor.capture(), any());
        else verify(client).detail(captor.capture(), any());
        return captor.getValue();
    }

    private static void login(Set<String> permissions)
    {
        var account = new SysUser();
        account.setUserName("test-operator");
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        new LoginUser(25L, 1L, account, permissions), "unused", List.of()));
    }

    private static final class TaskFixture
    {
        private final PythonPerformanceSchedulerClient scheduler =
                mock(PythonPerformanceSchedulerClient.class);
        private final EbayPriceAnalysisPythonClient priceAnalysis =
                mock(EbayPriceAnalysisPythonClient.class);
        private final IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
        private final SyncAlertService alerts = mock(SyncAlertService.class);
        private final PythonEbayStoreListingSyncTask task;

        private TaskFixture()
        {
            when(logs.start(anyString(), anyString(), anyString(), anyString(),
                    anyString(), isNull(), isNull())).thenReturn(77L);
            when(scheduler.runGoodcangProductInventory(anyString())).thenReturn(
                    Map.of("code", 0, "data", Map.of("status", "completed", "result",
                        Map.of("extract_rows", 9120, "ods_rows", 9120, "sync_batch_id", "gc-1"))));
            task = new PythonEbayStoreListingSyncTask(scheduler, priceAnalysis, logs, alerts);
        }
    }

    @Configuration
    @EnableMethodSecurity
    static class Config
    {
        @Bean
        EbayPriceAnalysisPythonClient client()
        {
            return mock(EbayPriceAnalysisPythonClient.class);
        }

        @Bean
        EbayPriceAnalysisController controller(EbayPriceAnalysisPythonClient client)
        {
            return new EbayPriceAnalysisController(client);
        }

        @Bean(name = "ss")
        Permissions permissions()
        {
            return new Permissions();
        }
    }

    public static class Permissions
    {
        Set<String> allowed = Set.of();

        public boolean hasPermi(String permission)
        {
            return allowed.contains(permission);
        }
    }
}
