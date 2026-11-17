package com.ruoyi.web.controller.finance;

import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.*;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class SalesDashboardControllerTest
{
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void forwardsRangeGroupsAndMultipart() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.salesDashboardReport(anyMap(), any())).thenReturn(Map.of("data", Map.of("currency", "CNY")));
        when(client.previewSalesHistory(any(), any())).thenReturn(Map.of("data", Map.of("row_count", 65)));
        var mvc = MockMvcBuilders.standaloneSetup(new SalesDashboardController(client)).build();
        mvc.perform(get("/finance/sales-dashboard/report").param("platform", "ebay")
                .param("startMonth", "2026-01").param("endMonth", "2026-09").param("groups", "DE,UK"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.currency").value("CNY"));
        verify(client).salesDashboardReport(Map.of("platform", "ebay", "start_month", "2026-01",
                "end_month", "2026-09", "groups_csv", "DE,UK"), null);
        mvc.perform(get("/finance/sales-dashboard/analysis").param("platform", "all")
                .param("startMonth", "2026-07").param("endMonth", "2026-09")
                .param("groups", "ebay:US,amz:US").param("granularity", "quarter"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.currency").value("CNY"));
        verify(client).salesDashboardReport(Map.of("platform", "all", "start_month", "2026-07",
                "end_month", "2026-09", "groups_csv", "ebay:US,amz:US", "granularity", "quarter"), null);
        var file = new MockMultipartFile("file", "history.xlsx", "application/octet-stream", new byte[] {1});
        mvc.perform(multipart("/finance/sales-dashboard/preview").file(file))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.row_count").value(65));
    }

    @Test void readPermissionDoesNotAuthorizeImport()
    {
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("test", "unused", List.of()));
            var controller = context.getBean(SalesDashboardController.class);
            var permissions = context.getBean(Permissions.class);
            var client = context.getBean(PerformancePythonClient.class);
            assertThrows(AccessDeniedException.class, () -> controller.options(null));
            assertThrows(AccessDeniedException.class, () -> controller.analysis("all", "2026-07", "2026-09", "", "quarter", null));
            assertThrows(AccessDeniedException.class, () -> controller.preview(null, null));
            verifyNoInteractions(client);
            permissions.allowed = Set.of("finance:salesDashboard:list");
            when(client.salesDashboardOptions(null)).thenReturn(Map.of("data", Map.of()));
            assertNotNull(controller.options(null));
            assertThrows(AccessDeniedException.class, () -> controller.preview(null, null));
            assertThrows(AccessDeniedException.class, () -> controller.importHistory(null, "sha", null));
            permissions.allowed = Set.of("finance:salesDashboard:list", "finance:salesDashboard:import");
            when(client.previewSalesHistory(null, null)).thenReturn(Map.of("data", Map.of()));
            assertNotNull(controller.preview(null, null));
        }
    }
    @Configuration @EnableMethodSecurity
    static class Config
    {
        @Bean PerformancePythonClient client() { return mock(PerformancePythonClient.class); }
        @Bean SalesDashboardController controller(PerformancePythonClient c) { return new SalesDashboardController(c); }
        @Bean(name="ss") Permissions permissions() { return new Permissions(); }
    }
    public static class Permissions
    {
        Set<String> allowed = Set.of();
        public boolean hasPermi(String permission) { return allowed.contains(permission); }
    }
}
