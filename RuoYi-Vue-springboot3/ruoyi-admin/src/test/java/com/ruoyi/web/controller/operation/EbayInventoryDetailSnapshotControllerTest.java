package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbayInventoryDetailPythonClient;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EbayInventoryDetailSnapshotControllerTest
{
    private static final String ROUTE = "/finance/ebay-inventory-detail/snapshot/recalculate";

    @AfterEach
    void clearSecurityContext()
    {
        SecurityContextHolder.clearContext();
    }

    @Test
    void recalculateUsesExistingWritePermissionPostAndUpdateAudit() throws Exception
    {
        var method = EbayInventoryDetailController.class.getMethod("recalculateSnapshot", String.class);
        assertEquals("@ss.hasPermi('operations:ebayInventoryDetail:import')",
                method.getAnnotation(PreAuthorize.class).value());
        assertArrayEquals(new String[] { "/snapshot/recalculate" }, method.getAnnotation(PostMapping.class).value());
        assertEquals("Ebay库存明细重新计算", method.getAnnotation(Log.class).title());
        assertEquals(BusinessType.UPDATE, method.getAnnotation(Log.class).businessType());
        assertEquals(1, method.getParameterCount());
        assertEquals("X-Request-ID", method.getParameters()[0].getAnnotation(RequestHeader.class).value());
    }

    @Test
    void recalculateIgnoresClientDatesFiltersAndBodyAndUnwrapsPythonData() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        Map<String, Object> data = Map.of("stat_date", "2026-09-16", "row_count", 37);
        when(client.recalculateSnapshot("recalculate-trace")).thenReturn(Map.of("code", 0, "data", data));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();

        mvc.perform(post(ROUTE)
                        .header("X-Request-ID", "recalculate-trace")
                        .param("statDate", "2000-01-01")
                        .param("stat_date", "2000-01-02")
                        .param("site", "德国")
                        .param("sku", "CLIENT-SKU")
                        .param("operator", "client-operator")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"statDate\":\"2000-01-03\",\"stat_date\":\"2000-01-04\",\"site\":\"英国\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.stat_date").value("2026-09-16"))
                .andExpect(jsonPath("$.data.row_count").value(37));

        verify(client).recalculateSnapshot("recalculate-trace");
        verifyNoMoreInteractions(client);
    }

    @Test
    void getCannotTriggerRecalculation() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        mvc.perform(get(ROUTE)).andExpect(status().isMethodNotAllowed());
        verifyNoInteractions(client);
    }

    @Test
    void missingWritePermissionStopsRecalculationBeforeCallingPython()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            var controller = context.getBean(EbayInventoryDetailController.class);
            var client = context.getBean(EbayInventoryDetailPythonClient.class);
            var permissions = context.getBean(TestPermissionService.class);

            assertThrows(AccessDeniedException.class, () -> controller.recalculateSnapshot("no-permission"));
            permissions.allowed = "operations:ebayInventoryDetail:list";
            assertThrows(AccessDeniedException.class, () -> controller.recalculateSnapshot("list-only"));
            permissions.allowed = "operations:ebayInventoryDetail:export";
            assertThrows(AccessDeniedException.class, () -> controller.recalculateSnapshot("export-only"));
            verifyNoInteractions(client);
        }
    }

    @Test
    void importPermissionAllowsRecalculationWithoutAClientDate()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            context.getBean(TestPermissionService.class).allowed = "operations:ebayInventoryDetail:import";
            var client = context.getBean(EbayInventoryDetailPythonClient.class);
            Map<String, Object> data = Map.of("stat_date", "2026-09-16", "row_count", 37);
            when(client.recalculateSnapshot(null)).thenReturn(Map.of("code", 0, "data", data));

            assertSame(data, context.getBean(EbayInventoryDetailController.class)
                    .recalculateSnapshot(null).get("data"));
            verify(client).recalculateSnapshot(null);
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
