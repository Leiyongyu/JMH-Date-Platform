package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.operation.customs.CustomsStaDeliveryDateService;
import java.util.List;
import java.util.Map;
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
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class CustomsStaDeliveryDateControllerTest
{
    public static class Permission
    {
        boolean allowed;
        public boolean hasPermi(String value) { return allowed && "customs:shipmentFee:list".equals(value); }
    }

    @Configuration
    @EnableMethodSecurity
    static class Config
    {
        @Bean(name="ss") Permission permission() { return new Permission(); }
        @Bean CustomsStaDeliveryDateService service() { return mock(CustomsStaDeliveryDateService.class); }
        @Bean CustomsStaDeliveryDateController controller(CustomsStaDeliveryDateService service)
        { return new CustomsStaDeliveryDateController(service); }
    }

    @Test
    void queriesRequireTheExistingStaViewPermission() throws Exception
    {
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("tester", "unused", List.of()));
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            var controller = context.getBean(CustomsStaDeliveryDateController.class);
            var service = context.getBean(CustomsStaDeliveryDateService.class);
            var query = query();
            assertThrows(AccessDeniedException.class, () -> controller.query(query));
            verifyNoInteractions(service);
            context.getBean(Permission.class).allowed = true;
            var result = Map.<String, Object>of("success", true, "options", List.of());
            when(service.query("plan-1", "FBA15MPTRK38", 12616L)).thenReturn(result);
            assertEquals(result, controller.query(query).get("data"));
        }
        finally { SecurityContextHolder.clearContext(); }
    }

    @Test
    void jsonQueryReturnsProviderDetailsAndNoCommitEndpointIsRegistered() throws Exception
    {
        var service = mock(CustomsStaDeliveryDateService.class);
        when(service.query(anyString(), anyString(), anyLong())).thenReturn(Map.of("success", true, "optionCount", 1,
                "options", List.of(Map.of("deliveryWindowOptionId", "dw-1", "startDate", "2026-11-01", "endDate", "2026-11-07"))));
        var mvc = MockMvcBuilders.standaloneSetup(new CustomsStaDeliveryDateController(service)).build();
        mvc.perform(post("/operations/customs/shipment-fee/delivery-dates/query")
                .contentType("application/json").content("{\"inboundPlanId\":\"plan-1\",\"shipmentNo\":\"FBA15MPTRK38\",\"sid\":\"12616\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.options[0].deliveryWindowOptionId").value("dw-1"));
        verify(service).query("plan-1", "FBA15MPTRK38", 12616L);
        mvc.perform(post("/operations/customs/shipment-fee/delivery-dates/commit")).andExpect(status().isNotFound());
    }

    @Test
    void queryErrorsRemainActionable()
    {
        var service = mock(CustomsStaDeliveryDateService.class);
        assertEquals(500, new CustomsStaDeliveryDateController(service).query(null).get("code"));
        verifyNoInteractions(service);
    }

    private CustomsStaDeliveryDateController.Query query()
    {
        var query = new CustomsStaDeliveryDateController.Query();
        query.setInboundPlanId("plan-1"); query.setShipmentNo("FBA15MPTRK38"); query.setSid(12616L);
        return query;
    }
}
