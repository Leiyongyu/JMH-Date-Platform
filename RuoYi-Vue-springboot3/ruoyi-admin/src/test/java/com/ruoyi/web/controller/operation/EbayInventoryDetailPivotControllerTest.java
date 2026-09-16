package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbayInventoryDetailPythonClient;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayInventoryDetailPivotControllerTest
{
    @AfterEach
    void clearSecurityContext()
    {
        SecurityContextHolder.clearContext();
    }

    @Test
    void pivotMapsAllFiltersAndUnwrapsPythonData()
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        Map<String, Object> data = Map.of("items", List.of(Map.of("owner", "李茫茫")),
                "pagination", Map.of("page", 2, "page_size", 50, "total", 30));
        when(client.pivot(anyMap(), eq("trace"))).thenReturn(Map.of("code", 0, "data", data));
        var controller = new EbayInventoryDetailController(client);
        var result = controller.pivot(" 2026-09-01 ", "2026-09-16", " 李茫茫 ", " 德国 ",
                2, 50, " stat_date ", " descending ", "trace");
        assertSame(data, result.get("data"));
        ArgumentCaptor<Map<String, Object>> params = ArgumentCaptor.forClass(Map.class);
        verify(client).pivot(params.capture(), eq("trace"));
        assertEquals(Map.of("start_date", "2026-09-01", "end_date", "2026-09-16",
                "owner", "李茫茫", "site", "德国", "page", 2, "page_size", 50,
                "sort_field", "stat_date", "sort_order", "descending"), params.getValue());
    }

    @Test
    void pivotClampsPaginationAndNormalizesBlankFilters()
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.pivot(anyMap(), any())).thenReturn(Map.of("data", Map.of()));
        var controller = new EbayInventoryDetailController(client);
        controller.pivot(" ", null, "\t", "", -1, 1000, null, null, null);
        controller.pivot(null, null, null, null, 2, -1, null, null, null);
        ArgumentCaptor<Map<String, Object>> params = ArgumentCaptor.forClass(Map.class);
        verify(client, times(2)).pivot(params.capture(), isNull());
        assertEquals(1, params.getAllValues().get(0).get("page"));
        assertEquals(200, params.getAllValues().get(0).get("page_size"));
        assertNull(params.getAllValues().get(0).get("start_date"));
        assertNull(params.getAllValues().get(0).get("owner"));
        assertNull(params.getAllValues().get(0).get("site"));
        assertEquals(1, params.getAllValues().get(1).get("page_size"));
    }

    @Test
    void pivotExportUsesAllMatchingRowsAndPreservesExcelResponse() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        byte[] bytes = new byte[] { 80, 75, 3, 4, -1, 0 };
        String disposition = "attachment; filename=pivot.xlsx; filename*=UTF-8''%E5%BA%93%E5%AD%98.xlsx";
        when(client.exportPivot(anyMap(), eq("export-trace")))
                .thenReturn(new EbayInventoryDetailPythonClient.ExcelFile(bytes, disposition));
        var response = new MockHttpServletResponse();
        new EbayInventoryDetailController(client).exportPivot("2026-09-01", "2026-09-16", " 王 ", " 英国 ",
                "sales_qty_30d", "descending", "export-trace", response);
        ArgumentCaptor<Map<String, Object>> params = ArgumentCaptor.forClass(Map.class);
        verify(client).exportPivot(params.capture(), eq("export-trace"));
        assertEquals(Map.of("start_date", "2026-09-01", "end_date", "2026-09-16", "owner", "王", "site", "英国",
                "sort_field", "sales_qty_30d", "sort_order", "descending"), params.getValue());
        assertFalse(params.getValue().containsKey("page"));
        assertFalse(params.getValue().containsKey("page_size"));
        assertEquals(EbayInventoryDetailPythonClient.EXCEL_CONTENT_TYPE, response.getContentType());
        assertEquals(disposition, response.getHeader("Content-Disposition"));
        assertEquals("Content-Disposition", response.getHeader("Access-Control-Expose-Headers"));
        assertEquals("no-store", response.getHeader("Cache-Control"));
        assertEquals(bytes.length, response.getContentLength());
        assertArrayEquals(bytes, response.getContentAsByteArray());
    }

    @Test
    void pivotRoutesUseExistingListAndExportPermissionsAndExportAudit() throws Exception
    {
        var pivot = EbayInventoryDetailController.class.getMethod("pivot", String.class, String.class,
                String.class, String.class, int.class, int.class, String.class, String.class, String.class);
        assertEquals("@ss.hasPermi('operations:ebayInventoryDetail:list')", pivot.getAnnotation(PreAuthorize.class).value());
        assertArrayEquals(new String[] { "/pivot" }, pivot.getAnnotation(GetMapping.class).value());
        var export = EbayInventoryDetailController.class.getMethod("exportPivot", String.class, String.class,
                String.class, String.class, String.class, String.class, String.class, HttpServletResponse.class);
        assertEquals("@ss.hasPermi('operations:ebayInventoryDetail:export')", export.getAnnotation(PreAuthorize.class).value());
        assertArrayEquals(new String[] { "/pivot/export" }, export.getAnnotation(GetMapping.class).value());
        assertEquals(BusinessType.EXPORT, export.getAnnotation(Log.class).businessType());
    }

    @Test
    void deniedPermissionsStopBothEndpointsBeforeCallingPython()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            var controller = context.getBean(EbayInventoryDetailController.class);
            var client = context.getBean(EbayInventoryDetailPythonClient.class);
            assertThrows(AccessDeniedException.class, () -> controller.pivot(null, null, null, null,
                    1, 50, null, null, null));
            assertThrows(AccessDeniedException.class, () -> controller.exportPivot(null, null, null, null,
                    null, null, null, new MockHttpServletResponse()));
            verifyNoInteractions(client);
        }
    }

    @Test
    void listPermissionDoesNotGrantExportPermission()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            context.getBean(TestPermissionService.class).allowed = "operations:ebayInventoryDetail:list";
            var client = context.getBean(EbayInventoryDetailPythonClient.class);
            when(client.pivot(anyMap(), any())).thenReturn(Map.of("data", Map.of("items", List.of())));
            var controller = context.getBean(EbayInventoryDetailController.class);
            assertNotNull(controller.pivot(null, null, null, null, 1, 50, null, null, null));
            assertThrows(AccessDeniedException.class, () -> controller.exportPivot(null, null, null, null,
                    null, null, null, new MockHttpServletResponse()));
            verify(client, never()).exportPivot(anyMap(), any());
        }
    }

    @Configuration
    @EnableMethodSecurity
    static class SecurityConfig
    {
        @Bean EbayInventoryDetailPythonClient client() { return mock(EbayInventoryDetailPythonClient.class); }
        @Bean EbayInventoryDetailController controller(EbayInventoryDetailPythonClient client)
        {
            return new EbayInventoryDetailController(client);
        }
        @Bean(name = "ss") TestPermissionService permissions() { return new TestPermissionService(); }
    }

    public static class TestPermissionService
    {
        String allowed;
        public boolean hasPermi(String permission) { return permission.equals(allowed); }
    }
}
