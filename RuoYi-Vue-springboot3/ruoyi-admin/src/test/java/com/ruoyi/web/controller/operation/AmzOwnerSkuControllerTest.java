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

class AmzOwnerSkuControllerTest
{
    @AfterEach void clearSecurityContext() { SecurityContextHolder.clearContext(); }

    @Test void unwrapsProtectedPythonResponseAndForwardsTrace() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.amzOwnerSkuSummary("owner-trace"))
                .thenReturn(Map.of("code", 0, "data", Map.of("total", 12)));
        var mvc = MockMvcBuilders.standaloneSetup(new AmzOwnerSkuController(client)).build();
        mvc.perform(get("/operations/amz/owner-sku/summary").header("X-Request-ID", "owner-trace"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(12));
        verify(client).amzOwnerSkuSummary("owner-trace");
        mvc.perform(post("/operations/amz/owner-sku/summary")).andExpect(status().isMethodNotAllowed());
        verifyNoMoreInteractions(client);
    }

    @Test void methodSecurityRejectsMissingOrUnrelatedPermissionBeforePython()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            var controller = context.getBean(AmzOwnerSkuController.class);
            var client = context.getBean(PerformancePythonClient.class);
            assertThrows(AccessDeniedException.class, () -> controller.summary(null));
            context.getBean(TestPermissions.class).allowed = "operations:ebayInventoryDetail:list";
            assertThrows(AccessDeniedException.class, () -> controller.summary(null));
            verifyNoInteractions(client);
        }
    }

    @Test void amzViewPermissionAllowsRead()
    {
        try (var context = new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(
                    new UsernamePasswordAuthenticationToken("test-user", "unused", List.of()));
            context.getBean(TestPermissions.class).allowed = "operations:amzReplenishment:list";
            var client = context.getBean(PerformancePythonClient.class);
            when(client.amzOwnerSkuSummary(null)).thenReturn(Map.of("data", Map.of("total", 3)));
            assertEquals(Map.of("total", 3), context.getBean(AmzOwnerSkuController.class).summary(null).get("data"));
            verify(client).amzOwnerSkuSummary(null);
        }
    }

    @Configuration
    @EnableMethodSecurity
    static class SecurityConfig
    {
        @Bean PerformancePythonClient client() { return mock(PerformancePythonClient.class); }
        @Bean AmzOwnerSkuController controller(PerformancePythonClient client) { return new AmzOwnerSkuController(client); }
        @Bean(name = "ss") TestPermissions permissions() { return new TestPermissions(); }
    }

    public static class TestPermissions
    {
        String allowed;
        public boolean hasPermi(String permission) { return permission.equals(allowed); }
    }
}
