package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.access.prepost.PreAuthorize;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentReviewControllerTest
{
    @Test
    void reviewWritesRequirePermissionAndUseAuthenticatedOperator() throws Exception
    {
        var client = mock(EbayReplenishmentV2PythonClient.class);
        when(client.saveReviewNote(anyMap(), any())).thenReturn(Map.of("data", Map.of()));
        when(client.confirmReview(anyMap(), any())).thenReturn(Map.of("data", Map.of()));
        var controller = new EbayReplenishmentV2Controller(client, null, null) {
            @Override public String getUsername() { return "actual-user"; }
        };
        controller.saveReviewNote(Map.of("operator", "forged", "text", "完整备注"), "trace");
        controller.confirmReview(Map.of("operator", "forged", "expected_version", 2), "trace");
        ArgumentCaptor<Map<String, Object>> body = ArgumentCaptor.forClass(Map.class);
        verify(client).saveReviewNote(body.capture(), eq("trace"));
        verify(client).confirmReview(body.capture(), eq("trace"));
        assertTrue(body.getAllValues().stream().allMatch(value -> "actual-user".equals(value.get("operator"))));
        for (String method : new String[] {"saveReviewNote", "confirmReview"}) {
            var annotation = EbayReplenishmentV2Controller.class.getMethod(method, Map.class, String.class).getAnnotation(PreAuthorize.class);
            assertEquals("@ss.hasPermi('operations:ebayReplenishmentV2:list')", annotation.value());
        }
    }

    @Test
    void confirmedAndPendingFiltersReachPythonWithoutLosingFalse()
    {
        var client = mock(EbayReplenishmentV2PythonClient.class);
        when(client.list(anyMap(), any())).thenReturn(Map.of("data", Map.of()));
        var controller = new EbayReplenishmentV2Controller(client, null, null);
        controller.list(null, null, null, null, null, true, false, true, 1, 50, null, null, false, false, null, "trace");
        controller.list(null, null, null, null, null, false, null, null, 1, 50, null, null, false, false, null, "trace");
        ArgumentCaptor<Map<String, Object>> params = ArgumentCaptor.forClass(Map.class);
        verify(client, times(2)).list(params.capture(), eq("trace"));
        assertEquals(true, params.getAllValues().get(0).get("operations_confirmed"));
        assertEquals(false, params.getAllValues().get(1).get("operations_confirmed"));
        assertEquals(false, params.getAllValues().get(0).get("operations_note_filled"));
        assertEquals(true, params.getAllValues().get(0).get("development_note_filled"));
        assertNull(params.getAllValues().get(1).get("operations_note_filled"));
    }

    @Test
    void versionedRefreshForwardsFlagsAndDoesNotMixInNewerLeadTimes()
    {
        var client = mock(EbayReplenishmentV2PythonClient.class);
        var leadTime = mock(com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2LeadTimeService.class);
        var payload = Map.of("calculation_version", "a".repeat(32), "items", java.util.List.of(Map.of("site", "德国", "sku", "BMW-1-2")));
        when(client.list(anyMap(), any())).thenReturn(Map.of("data", payload));
        var controller = new EbayReplenishmentV2Controller(client, leadTime, null);
        assertEquals(payload, controller.list(null, "BMW-1-2", null, null, null, null, null, null, 1, 50,
                "suggestedReplenishmentQty2", "desc", true, true, " 任雅婷 ", "trace").get("data"));
        ArgumentCaptor<Map<String, Object>> params = ArgumentCaptor.forClass(Map.class);
        verify(client).list(params.capture(), eq("trace"));
        assertEquals(true, params.getValue().get("refresh"));
        assertEquals(true, params.getValue().get("exact_sku"));
        assertEquals("任雅婷", params.getValue().get("principal_name"));
        verifyNoInteractions(leadTime);
    }
}
