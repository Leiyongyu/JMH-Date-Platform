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
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class HomeProductNatureControllerTest
{
    private static final List<String> VIEWS = List.of("summary","groups","owners","details","history","compare");
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void sixReadOnlyRoutesForwardPlatformFiltersAndTrace() throws Exception
    {
        var client=mock(PerformancePythonClient.class);
        when(client.productNature(anyString(),anyString(),anyMap(),eq("nature-trace")))
            .thenReturn(Map.of("data",Map.of("state","READY")));
        var mvc=MockMvcBuilders.standaloneSetup(new AmzOwnerSkuController(client),new EbayOwnerSkuController(client)).build();
        for (String platform:List.of("amz","ebay"))
        {
            for (String view:VIEWS)
            {
                String path="/operations/"+platform+"/owner-sku/nature/"+view;
                mvc.perform(get(path).param("month","2026-09").param("page_size","100")
                    .param("start_month","2025-10").param("end_month","2026-09").param("include_current","true")
                    .header("X-Request-ID","nature-trace"))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.data.state").value("READY"));
                verify(client).productNature(platform,view,Map.of("month","2026-09","page_size","100",
                    "start_month","2025-10","end_month","2026-09","include_current","true"),"nature-trace");
                mvc.perform(post(path)).andExpect(status().isMethodNotAllowed());
            }
        }
        verifyNoMoreInteractions(client);
    }

    @Test void everyViewChecksItsOwnPlatformPermissionBeforePython()
    {
        try(var context=new AnnotationConfigApplicationContext(SecurityConfig.class))
        {
            SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("test","unused",List.of()));
            var amz=context.getBean(AmzOwnerSkuController.class);
            var ebay=context.getBean(EbayOwnerSkuController.class);
            var client=context.getBean(PerformancePythonClient.class);
            var permissions=context.getBean(Permissions.class);
            for(String view:VIEWS)
            {
                assertThrows(AccessDeniedException.class,()->amz.nature(view,Map.of(),null));
                assertThrows(AccessDeniedException.class,()->ebay.nature(view,Map.of(),null));
            }
            verifyNoInteractions(client);
            when(client.productNature(anyString(),anyString(),anyMap(),isNull())).thenReturn(Map.of("data",Map.of()));
            permissions.allowed="operations:amzReplenishment:list";
            for(String view:VIEWS)
            {
                assertNotNull(amz.nature(view,Map.of(),null));
                assertThrows(AccessDeniedException.class,()->ebay.nature(view,Map.of(),null));
            }
            permissions.allowed="operations:ebayReplenishmentV2:list";
            for(String view:VIEWS)
            {
                assertNotNull(ebay.nature(view,Map.of(),null));
                assertThrows(AccessDeniedException.class,()->amz.nature(view,Map.of(),null));
            }
        }
    }

    @Configuration @EnableMethodSecurity
    static class SecurityConfig
    {
        @Bean PerformancePythonClient client(){return mock(PerformancePythonClient.class);}
        @Bean AmzOwnerSkuController amz(PerformancePythonClient c){return new AmzOwnerSkuController(c);}
        @Bean EbayOwnerSkuController ebay(PerformancePythonClient c){return new EbayOwnerSkuController(c);}
        @Bean(name="ss") Permissions permissions(){return new Permissions();}
    }
    public static class Permissions
    {
        String allowed;
        public boolean hasPermi(String p){return p.equals(allowed);}
    }
}
