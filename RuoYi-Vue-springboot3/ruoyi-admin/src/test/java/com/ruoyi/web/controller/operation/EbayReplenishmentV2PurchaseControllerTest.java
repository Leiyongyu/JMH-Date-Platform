package com.ruoyi.web.controller.operation;

import com.ruoyi.system.domain.procurement.PendingPurchaseSubmitRequest;
import com.ruoyi.system.service.procurement.PendingPurchaseService;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentV2PurchaseControllerTest
{
    public static class Permissions
    {
        Set<String> values = Set.of();
        public boolean hasPermi(String permission) { return values.contains(permission); }
    }

    @Configuration
    @EnableMethodSecurity
    static class Config
    {
        @Bean(name = "ss") Permissions permissions() { return new Permissions(); }
        @Bean PendingPurchaseService service() { return mock(PendingPurchaseService.class); }
        @Bean EbayReplenishmentV2PurchaseController controller(PendingPurchaseService service)
        {
            return new EbayReplenishmentV2PurchaseController(service) {
                @Override public String getUsername() { return "actual-user"; }
            };
        }
    }

    @Test
    void unrelatedPurchasePermissionCannotInvokeReplenishmentPurchaseEndpoint()
    {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken("actual-user", "unused", List.of()));
        try (var context = new AnnotationConfigApplicationContext(Config.class))
        {
            var controller = context.getBean(EbayReplenishmentV2PurchaseController.class);
            var permissions = context.getBean(Permissions.class);
            var service = context.getBean(PendingPurchaseService.class);
            var request = new PendingPurchaseSubmitRequest();
            request.setSite("德国"); request.setSku("BMW-1-2"); request.setPurchaseQuantity(10);
            for (Set<String> denied : List.of(Set.<String>of(),
                    Set.of("operations:ebayReplenishmentV2:list", "procurement:pendingPurchase:add"),
                    Set.of("operations:ebayReplenishmentV2:purchase")))
            {
                permissions.values = denied;
                assertThrows(AccessDeniedException.class, () -> controller.submit(request));
            }
            verifyNoInteractions(service);
            permissions.values = Set.of("operations:ebayReplenishmentV2:list", "operations:ebayReplenishmentV2:purchase");
            assertEquals(200, controller.submit(request).get("code"));
            verify(service).submit(request, "actual-user");
        }
        finally { SecurityContextHolder.clearContext(); }
    }
}
