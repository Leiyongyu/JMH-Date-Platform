package com.ruoyi.web.controller.finance;

import com.ruoyi.framework.web.service.PermissionService;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MonthlyInventoryReportControllerTest
{
    @Test
    void exportIncludesOnlyDimensionsAllowedForCurrentUser()
    {
        var client = mock(PerformancePythonClient.class);
        var permissions = mock(PermissionService.class);
        when(permissions.hasPermi("finance:monthlyInventoryReport:viewGroup"))
                .thenReturn(true);
        when(permissions.hasPermi("finance:monthlyInventoryReport:viewOwner"))
                .thenReturn(true);
        when(client.exportMonthlyInventoryReport("2026-08", "VISIBLE:GROUP,OWNER", null))
                .thenReturn(new byte[] {1, 2, 3});

        var controller = new MonthlyInventoryReportController(client, permissions);
        var response = controller.export("2026-08", "ALL", null);

        assertEquals(200, response.getStatusCode().value());
        assertArrayEquals(new byte[] {1, 2, 3}, response.getBody());
        verify(client).exportMonthlyInventoryReport("2026-08", "VISIBLE:GROUP,OWNER", null);
        assertThrows(AccessDeniedException.class,
                () -> controller.export("2026-08", "STORE", null));
        verifyNoMoreInteractions(client);
    }

    @Test
    void dimensionSummaryRejectsMissingPermission()
    {
        var client = mock(PerformancePythonClient.class);
        var permissions = mock(PermissionService.class);
        var controller = new MonthlyInventoryReportController(client, permissions);

        assertThrows(AccessDeniedException.class,
                () -> controller.dimensionSummary("STORE", "2026-08", null));
        verifyNoInteractions(client);

        when(permissions.hasPermi("finance:monthlyInventoryReport:viewOwner"))
                .thenReturn(true);
        when(client.monthlyInventoryReportDimensionSummary("OWNER", "2026-08", null))
                .thenReturn(Map.of("data", Map.of("items", java.util.List.of())));
        assertNotNull(controller.dimensionSummary("OWNER", "2026-08", null));
    }

    @Test
    void exportWithOnePermissionNeverRequestsOtherSheets()
    {
        var client = mock(PerformancePythonClient.class);
        var permissions = mock(PermissionService.class);
        when(permissions.hasPermi("finance:monthlyInventoryReport:viewStore"))
                .thenReturn(true);
        when(client.exportMonthlyInventoryReport("2026-08", "VISIBLE:STORE", null))
                .thenReturn(new byte[] {1});
        var controller = new MonthlyInventoryReportController(client, permissions);

        assertEquals(200, controller.export("2026-08", "ALL", null)
                .getStatusCode().value());
        verify(client).exportMonthlyInventoryReport("2026-08", "VISIBLE:STORE", null);
    }

    @Test
    void groupSummaryRequiresGroupViewPermission() throws Exception
    {
        var annotation = MonthlyInventoryReportController.class
                .getMethod("summary", String.class, String.class)
                .getAnnotation(PreAuthorize.class);
        assertTrue(annotation.value().contains("monthlyInventoryReport:viewGroup"));
        var detailsAnnotation = MonthlyInventoryReportController.class
                .getMethod("list", String.class, String.class, String.class,
                        String.class, String.class, int.class, int.class,
                        String.class)
                .getAnnotation(PreAuthorize.class);
        assertTrue(detailsAnnotation.value().contains("monthlyInventoryReport:viewGroup"));
    }
}
