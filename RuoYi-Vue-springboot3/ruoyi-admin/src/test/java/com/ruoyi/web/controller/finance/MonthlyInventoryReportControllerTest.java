package com.ruoyi.web.controller.finance;

import com.ruoyi.framework.web.service.PermissionService;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.Map;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.multipart.MultipartFile;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MonthlyInventoryReportControllerTest
{
    @Test
    void purchaseOrderSyncReturnsBackgroundJobAndStatus() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        var controller = new MonthlyInventoryReportController(client, mock(PermissionService.class));
        when(client.syncMonthlyInventoryPurchaseOrder("request-1"))
                .thenReturn(Map.of("data", Map.of("request_id", "job-1", "status", "queued")));
        assertEquals(Map.of("request_id", "job-1", "status", "queued"),
                controller.syncPurchaseOrder("request-1").get("data"));
        when(client.monthlyInventoryPurchaseOrderStatus("2026-10", "job-1", "request-2"))
                .thenReturn(Map.of("data", Map.of("running", true)));
        assertEquals(Map.of("running", true),
                controller.purchaseOrderSyncStatus("2026-10", "job-1", "request-2").get("data"));
        for (var method : List.of(
                MonthlyInventoryReportController.class.getMethod("syncPurchaseOrder", String.class),
                MonthlyInventoryReportController.class.getMethod("purchaseOrderSyncStatus", String.class, String.class, String.class)))
            assertTrue(method.getAnnotation(PreAuthorize.class).value().contains("monthlyInventoryReport:edit"));
    }

    @AfterEach
    void clearSecurityContext()
    {
        SecurityContextHolder.clearContext();
    }

    private void authenticate(Long userId)
    {
        LoginUser user = new LoginUser();
        user.setUserId(userId);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(user, null, List.of()));
    }

    @Test
    void historyPreviewAndImportRequireAdminRoleOrBuiltInSuperAdmin()
    {
        var client = mock(PerformancePythonClient.class);
        var permissions = mock(PermissionService.class);
        var controller = new MonthlyInventoryReportController(
                client, permissions);
        var file = mock(MultipartFile.class);
        authenticate(101L);
        assertThrows(AccessDeniedException.class,
                () -> controller.previewHistory(file, null));
        assertThrows(AccessDeniedException.class,
                () -> controller.importHistory(file, "digest", null));
        verifyNoInteractions(client);

        when(permissions.hasRole("admin")).thenReturn(true);
        when(client.previewMonthlyInventoryHistory(file, null))
                .thenReturn(Map.of("data", Map.of("sheets", List.of())));
        when(client.importMonthlyInventoryHistory(file, "digest", null))
                .thenReturn(Map.of("data", Map.of("imported_months", List.of())));
        assertEquals(200, controller.previewHistory(file, null).get("code"));
        assertEquals(200, controller.importHistory(file, "digest", null).get("code"));

        when(permissions.hasRole("admin")).thenReturn(false);
        authenticate(1L);
        assertEquals(200, controller.previewHistory(file, null).get("code"));
        assertEquals(200, controller.importHistory(file, "digest", null).get("code"));
        verify(client, times(2)).previewMonthlyInventoryHistory(file, null);
        verify(client, times(2)).importMonthlyInventoryHistory(file, "digest", null);
    }

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
    void ownerTrendRequiresOwnerViewPermission() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        var permissions = mock(PermissionService.class);
        var controller = new MonthlyInventoryReportController(client, permissions);

        assertThrows(AccessDeniedException.class,
                () -> controller.ownerTrend("2026-06", "2026-09", null));
        verifyNoInteractions(client);

        when(permissions.hasPermi("finance:monthlyInventoryReport:viewOwner")).thenReturn(true);
        when(client.monthlyInventoryReportOwnerTrend("2026-06", "2026-09", "req-1"))
                .thenReturn(Map.of("data", Map.of("months", List.of("2026-06"))));
        assertEquals(Map.of("months", List.of("2026-06")),
                controller.ownerTrend("2026-06", "2026-09", "req-1").get("data"));
        assertTrue(MonthlyInventoryReportController.class
                .getMethod("ownerTrend", String.class, String.class, String.class)
                .getAnnotation(PreAuthorize.class).value().contains("monthlyInventoryReport:viewOwner"));
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
