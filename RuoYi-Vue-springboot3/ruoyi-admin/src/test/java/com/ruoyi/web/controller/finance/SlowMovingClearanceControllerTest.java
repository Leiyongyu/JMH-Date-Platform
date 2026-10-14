package com.ruoyi.web.controller.finance;

import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class SlowMovingClearanceControllerTest
{
    @Test
    void dimensionsForwardSelectedMonthAndGroup() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        var data = Map.of("dimension", "SITE", "items", List.of(Map.of("dimension_key", "US")));
        when(client.clearanceDimensions("2026-10", "EBAY-1", null, "test-id"))
                .thenReturn(Map.of("data", data));
        var controller = new SlowMovingClearanceController(client);
        var response = controller.dimensions("2026-10", "EBAY-1", null, "test-id");
        assertEquals(200, response.get("code"));
        assertEquals(data, response.get("data"));
        verify(client).clearanceDimensions("2026-10", "EBAY-1", null, "test-id");
        var permission = SlowMovingClearanceController.class.getMethod(
                "dimensions", String.class, String.class, String.class, String.class)
                .getAnnotation(PreAuthorize.class);
        assertEquals("@ss.hasPermi('finance:slowMovingClearance:list')", permission.value());
    }

    @Test
    void failureIsNotReturnedAsEmptySuccessfulData()
    {
        var client = mock(PerformancePythonClient.class);
        when(client.clearanceDimensions("2026-10", "EU", null, null))
                .thenThrow(new IllegalStateException("查询失败"));
        var response = new SlowMovingClearanceController(client).dimensions("2026-10", "EU", null, null);
        assertEquals(500, response.get("code"));
        assertEquals("查询失败", response.get("msg"));
    }

    @Test
    void ownerDrilldownForwardsSite()
    {
        var client = mock(PerformancePythonClient.class);
        when(client.clearanceDimensions("2026-10", "EBAY-1", "US", "trace"))
                .thenReturn(Map.of("data", Map.of("dimension", "OWNER")));
        var response = new SlowMovingClearanceController(client).dimensions("2026-10", "EBAY-1", "US", "trace");
        assertEquals(200, response.get("code"));
        verify(client).clearanceDimensions("2026-10", "EBAY-1", "US", "trace");
    }

    @Test
    void ownerDialogDefaultsToAllSitesAndRequiresListPermission() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.clearanceOwners("2026-10", null, "trace"))
                .thenReturn(Map.of("data", Map.of("dimension", "OWNER")));
        var controller = new SlowMovingClearanceController(client);
        assertEquals(200, controller.owners("2026-10", null, "trace").get("code"));
        verify(client).clearanceOwners("2026-10", null, "trace");
        when(client.clearanceOwners("2026-10", "UK", null)).thenReturn(Map.of("data", Map.of()));
        assertEquals(200, controller.owners("2026-10", "UK", null).get("code"));
        verify(client).clearanceOwners("2026-10", "UK", null);
        var permission = SlowMovingClearanceController.class.getMethod("owners", String.class, String.class, String.class)
                .getAnnotation(PreAuthorize.class);
        assertEquals("@ss.hasPermi('finance:slowMovingClearance:list')", permission.value());
    }

    @Test
    void monthlyExportForwardsSelectedMonthAndRequiresListPermission() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        byte[] workbook = new byte[] {80, 75, 3, 4};
        when(client.exportClearanceMonthlySummary("2026-09", "export-trace")).thenReturn(workbook);
        var response = new SlowMovingClearanceController(client).exportMonthlySummary("2026-09", "export-trace");
        assertArrayEquals(workbook, response.getBody());
        assertEquals("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                response.getHeaders().getContentType().toString());
        assertTrue(response.getHeaders().getFirst("Content-Disposition").contains("2026-09"));
        verify(client).exportClearanceMonthlySummary("2026-09", "export-trace");
        var permission = SlowMovingClearanceController.class.getMethod("exportMonthlySummary", String.class, String.class)
                .getAnnotation(PreAuthorize.class);
        assertEquals("@ss.hasPermi('finance:slowMovingClearance:list')", permission.value());
    }
}
