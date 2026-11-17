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

class AmzPriceTierControllerTest
{
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void routesForwardTraceAndUnwrapResponse() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.amzPriceTierSummary("trace")).thenReturn(Map.of("data", Map.of("state", "READY")));
        when(client.refreshAmzPriceTier("trace")).thenReturn(Map.of("data", Map.of("state", "READY")));
        var mvc = MockMvcBuilders.standaloneSetup(new AmzPriceTierController(client)).build();
        mvc.perform(get("/operations/amz/price-tier/summary").header("X-Request-ID", "trace"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.state").value("READY"));
        mvc.perform(post("/operations/amz/price-tier/refresh").header("X-Request-ID", "trace"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.state").value("READY"));
        mvc.perform(get("/operations/amz/price-tier/refresh")).andExpect(status().isMethodNotAllowed());
        verify(client).amzPriceTierSummary("trace");
        verify(client).refreshAmzPriceTier("trace");
        verifyNoMoreInteractions(client);
    }

    @Test void permissionProtectsBothReadAndRefresh()
    {
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("u", "x", List.of()));
            var controller = context.getBean(AmzPriceTierController.class);
            var client = context.getBean(PerformancePythonClient.class);
            var perms = context.getBean(Permissions.class);
            assertThrows(AccessDeniedException.class, () -> controller.summary(null));
            assertThrows(AccessDeniedException.class, () -> controller.refresh(null));
            perms.allowed = "operations:ebayReplenishmentV2:list";
            assertThrows(AccessDeniedException.class, () -> controller.refresh(null));
            verifyNoInteractions(client);
            perms.allowed = "operations:amzReplenishment:list";
            when(client.amzPriceTierSummary(null)).thenReturn(Map.of("data", Map.of("state", "READY")));
            when(client.refreshAmzPriceTier(null)).thenReturn(Map.of("data", Map.of("state", "READY")));
            assertNotNull(controller.summary(null).get("data"));
            assertNotNull(controller.refresh(null).get("data"));
        }
    }

    @Configuration @EnableMethodSecurity
    static class Config
    {
        @Bean PerformancePythonClient client() { return mock(PerformancePythonClient.class); }
        @Bean AmzPriceTierController controller(PerformancePythonClient client) { return new AmzPriceTierController(client); }
        @Bean(name="ss") Permissions permissions() { return new Permissions(); }
    }
    public static class Permissions
    {
        String allowed;
        public boolean hasPermi(String permission) { return permission.equals(allowed); }
    }
}
