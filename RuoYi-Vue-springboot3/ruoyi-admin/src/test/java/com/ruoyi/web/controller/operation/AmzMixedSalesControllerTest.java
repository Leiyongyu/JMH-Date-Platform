package com.ruoyi.web.controller.operation;

import com.ruoyi.system.domain.operation.AmzMixedSalesQuery;
import com.ruoyi.system.service.operation.AmzMixedSalesService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class AmzMixedSalesControllerTest
{
    @Test
    void unionAndSiteDetailsAreDelegatedToPythonWithBoundFilters()
    {
        var stores = mock(AmzMixedSalesService.class);
        var client = mock(EbayReplenishmentV2PythonClient.class);
        when(client.mixedSales(anyMap(), anyBoolean(), isNull())).thenReturn(Map.of("data", Map.of("total", 2)));
        var controller = new AmzMixedSalesController(stores, client);
        var query = new AmzMixedSalesQuery();
        query.setSku("SKU"); query.setSid(12616); query.setCalculationVersion("a".repeat(32));
        query.setStatMonth("2026-10");
        query.setAgeBucket(4);
        query.setPageSize(999); query.setPageNum(-1);
        assertNotNull(controller.list(query));
        verify(client).mixedSales(argThat(p -> "amz".equals(p.get("platform"))
                && "SKU".equals(p.get("sku")) && Integer.valueOf(12616).equals(p.get("sid"))
                && Integer.valueOf(200).equals(p.get("page_size")) && Integer.valueOf(1).equals(p.get("page"))
                && "a".repeat(32).equals(p.get("calculation_version"))
                && Integer.valueOf(4).equals(p.get("age_bucket"))
                && "2026-10".equals(p.get("stat_month"))), eq(false), isNull());
        assertNotNull(controller.details(query));
        verify(client).mixedSales(anyMap(), eq(true), isNull());
        verifyNoInteractions(stores);
    }

    @Test
    void listDetailsAndStoreOptionsRequireIndependentMixedSalesPermission() throws Exception
    {
        for (var method : AmzMixedSalesController.class.getDeclaredMethods())
            if (java.util.Set.of("list", "details", "stores").contains(method.getName()))
                assertEquals("@ss.hasPermi('operations:mixedSales:list')", method.getAnnotation(PreAuthorize.class).value());
    }
}
