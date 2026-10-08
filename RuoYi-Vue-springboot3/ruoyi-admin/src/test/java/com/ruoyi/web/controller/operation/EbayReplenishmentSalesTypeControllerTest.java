package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.access.prepost.PreAuthorize;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentSalesTypeControllerTest
{
    @Test
    void saveUsesIndependentPermissionAndAuthenticatedOperator() throws Exception
    {
        var annotation = EbayReplenishmentV2Controller.class
                .getMethod("saveSalesType", Map.class, String.class).getAnnotation(PreAuthorize.class);
        assertEquals("@ss.hasPermi('operations:ebayReplenishmentV2:editSalesType')", annotation.value());
        var client = mock(EbayReplenishmentV2PythonClient.class);
        when(client.saveSalesType(anyMap(), any())).thenReturn(Map.of("data", Map.of()));
        var controller = new EbayReplenishmentV2Controller(client, null, null)
        {
            @Override public String getUsername() { return "actual-user"; }
        };
        controller.saveSalesType(Map.of("site", "德国", "sku", "FULL-SKU",
                "sales_type", "BRUSH", "operator", "forged-user"), "request-1");
        ArgumentCaptor<Map<String, Object>> body = ArgumentCaptor.forClass(Map.class);
        verify(client).saveSalesType(body.capture(), eq("request-1"));
        assertEquals("actual-user", body.getValue().get("operator"));
        assertEquals("FULL-SKU", body.getValue().get("sku"));
    }
}
