package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.Arrays;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.access.prepost.PreAuthorize;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentHierarchyControllerTest
{
    @Test
    void hierarchyUsesListPermissionAndForwardsPinnedParentAndFilters()
    {
        var method = Arrays.stream(EbayReplenishmentV2Controller.class.getMethods())
                .filter(item -> item.getName().equals("hierarchy")).findFirst().orElseThrow();
        assertEquals("@ss.hasPermi('operations:ebayReplenishmentV2:list')",
                method.getAnnotation(PreAuthorize.class).value());
        var client = mock(EbayReplenishmentV2PythonClient.class);
        when(client.hierarchy(anyMap(), any())).thenReturn(Map.of("data", Map.of("items", java.util.List.of())));
        var controller = new EbayReplenishmentV2Controller(client, null, null);
        controller.hierarchy("sku", "英国", " FRD-70327 ", "70327", "A", "老品",
                "NORMAL", true, false, true, "任雅婷", "suggestedReplenishmentQty2", "ascending",
                "a".repeat(32), -1, 999, false, "hierarchy-request");
        ArgumentCaptor<Map<String, Object>> params = ArgumentCaptor.forClass(Map.class);
        verify(client).hierarchy(params.capture(), eq("hierarchy-request"));
        var sent = params.getValue();
        assertEquals("sku", sent.get("hierarchy_level"));
        assertEquals("FRD-70327", sent.get("brand_core"));
        assertEquals("英国", sent.get("site"));
        assertEquals("任雅婷", sent.get("principal_name"));
        assertEquals(true, sent.get("operations_confirmed"));
        assertEquals(false, sent.get("operations_note_filled"));
        assertEquals(true, sent.get("development_note_filled"));
        assertEquals("a".repeat(32), sent.get("calculation_version"));
        assertEquals("asc", sent.get("sort_order"));
        assertEquals(1, sent.get("page"));
        assertEquals(200, sent.get("page_size"));
        assertEquals(false, sent.get("refresh"));
    }
}
