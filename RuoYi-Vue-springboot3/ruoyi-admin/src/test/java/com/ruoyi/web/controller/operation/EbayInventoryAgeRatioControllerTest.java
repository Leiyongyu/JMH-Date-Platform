package com.ruoyi.web.controller.operation;

import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.system.service.operation.ebay.EbayInventoryDetailPythonClient;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EbayInventoryAgeRatioControllerTest
{
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void readForwardsOnlyStatDate() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.ageRatio(anyMap(), any())).thenReturn(Map.of("data", Map.of("owners", List.of())));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        mvc.perform(get("/finance/ebay-inventory-detail/age-ratio").param("statDate", "2026-09-28"))
                .andExpect(status().isOk());
        verify(client).ageRatio(eq(Map.of("stat_date", "2026-09-28")), isNull());
    }

    @Test void readForwardsDateRange() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.ageRatio(anyMap(), any())).thenReturn(Map.of("data", Map.of("owners", List.of())));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        mvc.perform(get("/finance/ebay-inventory-detail/age-ratio")
                .param("startDate", "2026-09-01").param("endDate", "2026-09-29"))
                .andExpect(status().isOk());
        verify(client).ageRatio(argThat(params -> "2026-09-01".equals(params.get("start_date"))
                && "2026-09-29".equals(params.get("end_date"))), isNull());
    }

    @Test void refreshRejectsGetAndIgnoresClientAmountsDates() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.recalculateAgeRatio(any())).thenReturn(Map.of("data", Map.of("stat_date", "2026-09-29")));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        String url = "/finance/ebay-inventory-detail/age-ratio/recalculate";
        mvc.perform(post(url).contentType(MediaType.APPLICATION_JSON)
                .content("{\"statDate\":\"2020-01-01\",\"total_value\":999}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.stat_date").value("2026-09-29"));
        verify(client).recalculateAgeRatio(null);
        mvc.perform(get(url)).andExpect(status().isMethodNotAllowed());
        var method = EbayInventoryDetailController.class.getMethod("recalculateAgeRatio", String.class);
        assertEquals("@ss.hasPermi('operations:ebayInventoryDetail:import')", method.getAnnotation(PreAuthorize.class).value());
        assertEquals(BusinessType.UPDATE, method.getAnnotation(Log.class).businessType());
    }

    @Test void realMethodSecurityRejectsReadOnlyAndAllowsExistingWritePermission()
    {
        try (var context = new AnnotationConfigApplicationContext(EbayInventoryDetailSnapshotControllerTest.SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("test", "unused", List.of()));
            var permissions = context.getBean(EbayInventoryDetailSnapshotControllerTest.TestPermissionService.class);
            var controller = context.getBean(EbayInventoryDetailController.class);
            var client = context.getBean(EbayInventoryDetailPythonClient.class);
            permissions.allowed = "operations:ebayInventoryDetail:list";
            assertThrows(AccessDeniedException.class, () -> controller.recalculateAgeRatio(null));
            verifyNoInteractions(client);
            permissions.allowed = "operations:ebayInventoryDetail:import";
            when(client.recalculateAgeRatio(null)).thenReturn(Map.of("data", Map.of("stat_date", "2026-09-29")));
            assertEquals("2026-09-29", ((Map<?, ?>) controller.recalculateAgeRatio(null).get("data")).get("stat_date"));
        }
    }
}
