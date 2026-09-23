package com.ruoyi.web.controller.finance;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.*;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class HomeInventoryControllerTest
{
    @Test void methodSecurityChecksEveryRequiredSourcePermission()
    {
        try(var context=new AnnotationConfigApplicationContext(Config.class))
        {
            SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken("u","p",List.of()));
            var controller=context.getBean(HomeInventoryController.class);
            var perms=context.getBean(Permissions.class);
            var client=context.getBean(PerformancePythonClient.class);
            assertThrows(AccessDeniedException.class,()->controller.summary(null,null));
            perms.allowed.add("finance:monthlyInventoryReport:list");
            assertThrows(AccessDeniedException.class,()->controller.summary(null,null));
            perms.allowed.add("finance:slowMovingClearance:list");
            when(client.homeInventorySummary(null,null)).thenReturn(Map.of("data",Map.of("report_month","2026-09")));
            assertNotNull(controller.summary(null,null).get("data"));
            assertThrows(AccessDeniedException.class,()->controller.sku("2026-09",null));
            perms.allowed.add("operations:amzReplenishment:list");
            assertThrows(AccessDeniedException.class,()->controller.snapshot(null));
            perms.allowed.add("operations:ebayReplenishmentV2:list");
            when(client.captureHomeInventorySku(null)).thenReturn(Map.of("data",Map.of("total",30)));
            assertNotNull(controller.snapshot(null).get("data"));
            verify(client).captureHomeInventorySku(null);
        }
        finally { SecurityContextHolder.clearContext(); }
    }
    @Configuration @EnableMethodSecurity static class Config
    {
        @Bean PerformancePythonClient client(){return mock(PerformancePythonClient.class);}
        @Bean HomeInventoryController controller(PerformancePythonClient client){return new HomeInventoryController(client);}
        @Bean(name="ss") Permissions permissions(){return new Permissions();}
    }
    public static class Permissions
    {
        Set<String> allowed=new HashSet<>();
        public boolean hasPermi(String permission){return allowed.contains(permission);}
    }
}
