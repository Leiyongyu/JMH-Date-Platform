package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EbayOwnerSkuControllerTest
{
    @AfterEach void clearSecurityContext() { SecurityContextHolder.clearContext(); }

    @Test void unwrapsProtectedPythonResponseAndForwardsTrace() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.ebayOwnerSkuSummary("owner-trace"))
                .thenReturn(Map.of("code", 0, "data", Map.of("total", 12)));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayOwnerSkuController(client)).build();
        mvc.perform(get("/operations/ebay/owner-sku/summary").header("X-Request-ID", "owner-trace"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(12));
        verify(client).ebayOwnerSkuSummary("owner-trace");
        mvc.perform(post("/operations/ebay/owner-sku/summary")).andExpect(status().isMethodNotAllowed());
        verifyNoMoreInteractions(client);
    }

    @Test void methodSecurityRejectsMissingOrUnrelatedPermissionBeforePython()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            var controller = context.getBean(EbayOwnerSkuController.class);
            var client = context.getBean(PerformancePythonClient.class);
            assertThrows(AccessDeniedException.class, () -> controller.summary(null));
            context.getBean(TestPermissions.class).allowed = "operations:amzReplenishment:list";
            assertThrows(AccessDeniedException.class, () -> controller.summary(null));
            verifyNoInteractions(client);
        }
    }

    @Test void ebayViewPermissionAllowsRead()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            context.getBean(TestPermissions.class).allowed = "operations:ebayReplenishmentV2:list";
            var client = context.getBean(PerformancePythonClient.class);
            when(client.ebayOwnerSkuSummary(null)).thenReturn(Map.of("data", Map.of("total", 3)));
            assertEquals(Map.of("total", 3), context.getBean(EbayOwnerSkuController.class).summary(null).get("data"));
            verify(client).ebayOwnerSkuSummary(null);
        }
    }

    @Configuration
    @EnableMethodSecurity
    static class SecurityConfig
    {
        @Bean PerformancePythonClient client() { return mock(PerformancePythonClient.class); }
        @Bean EbayOwnerSkuController controller(PerformancePythonClient client) { return new EbayOwnerSkuController(client); }
        @Bean(name = "ss") TestPermissions permissions() { return new TestPermissions(); }
    }

    public static class TestPermissions
    {
        String allowed;
        public boolean hasPermi(String permission) { return permission.equals(allowed); }
    }
}
