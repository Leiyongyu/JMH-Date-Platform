package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.access.prepost.PreAuthorize;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayMixedSalesControllerTest
{
    @Test
    void priceQueryUsesMixedSalesPermissionAndForwardsMonthAndSku() throws Exception
    {
        var method=EbayMixedSalesController.class.getMethod("prices",String.class,String.class,String.class,int.class,int.class,String.class);
        assertEquals("@ss.hasPermi('operations:mixedSales:list')",method.getAnnotation(PreAuthorize.class).value());
        var client=mock(EbayReplenishmentV2PythonClient.class);
        when(client.mixedSalesPrices(anyMap(),any())).thenReturn(Map.of("data",Map.of("items",java.util.List.of())));
        new EbayMixedSalesController(client).prices("FRD-70327-0076","英国","2026-10",-1,999,"prices-request");
        ArgumentCaptor<Map<String,Object>> args=ArgumentCaptor.forClass(Map.class);
        verify(client).mixedSalesPrices(args.capture(),eq("prices-request"));
        assertEquals("2026-10",args.getValue().get("stat_month"));
        assertEquals("FRD-70327-0076",args.getValue().get("sku"));
        assertEquals(1,args.getValue().get("page"));
        assertEquals(200,args.getValue().get("page_size"));
    }

    @Test
    void mixedSalesPermissionAndPinnedFiltersAreForwardedWithoutReplenishmentPagePermission() throws Exception
    {
        var method = EbayMixedSalesController.class.getMethod("list", String.class, String.class, String.class,
                int.class, int.class, String.class, String.class, String.class, String.class, String.class, HttpServletRequest.class);
        assertEquals("@ss.hasPermi('operations:mixedSales:list')", method.getAnnotation(PreAuthorize.class).value());
        var client = mock(EbayReplenishmentV2PythonClient.class);
        when(client.mixedSales(anyMap(), anyBoolean(), any())).thenReturn(Map.of("data", Map.of("items", java.util.List.of())));
        var request = mock(HttpServletRequest.class);
        when(request.getRequestURI()).thenReturn("/operations/mixed-sales/ebay/details");
        when(request.getParameter("ageOperator")).thenReturn("gt");
        when(request.getParameter("ageDays")).thenReturn("180");
        var controller = new EbayMixedSalesController(client);
        controller.list(" 英国 ", "FRD-70327-0076", " 产品 ", -1, 999, "sales30d", "asc", "a".repeat(32), "2026-10", "trace", request);
        ArgumentCaptor<Map<String,Object>> params = ArgumentCaptor.forClass(Map.class);
        verify(client).mixedSales(params.capture(), eq(true), eq("trace"));
        assertEquals("英国", params.getValue().get("site"));
        assertEquals("产品", params.getValue().get("product_name"));
        assertEquals(1, params.getValue().get("page"));
        assertEquals(200, params.getValue().get("page_size"));
        assertEquals("a".repeat(32), params.getValue().get("calculation_version"));
        assertEquals("2026-10", params.getValue().get("stat_month"));
        assertEquals("gt", params.getValue().get("age_operator"));
        assertEquals("180", params.getValue().get("age_days"));
    }
}
