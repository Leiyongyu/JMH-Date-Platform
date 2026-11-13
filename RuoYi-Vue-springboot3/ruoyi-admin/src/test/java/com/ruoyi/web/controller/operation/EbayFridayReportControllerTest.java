package com.ruoyi.web.controller.operation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.mock.web.MockMultipartFile;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.system.service.operation.ebay.EbayFridayReportPythonClient;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class EbayFridayReportControllerTest
{
    @Test
    void onlyWhitelistedParamsAreForwardedInSnakeCase()
    {
        Map<String, String> query = EbayFridayReportController.query(Map.of(
                "reportDate", "2026-11-13", "storeName", "pieces_saleshop", "principalName", "房伟",
                "pageNum", "2", "pageSize", "50", "flag", " mismatch ", "evil", "x", "brand", ""),
                Set.of("reportDate", "storeName", "principalName", "pageNum", "pageSize", "flag", "brand"));
        assertEquals("2026-11-13", query.get("report_date"));
        assertEquals("pieces_saleshop", query.get("store_name"));
        assertEquals("房伟", query.get("principal_name"));
        assertEquals("2", query.get("page"));
        assertEquals("50", query.get("page_size"));
        assertEquals("mismatch", query.get("flag"));
        assertFalse(query.containsKey("evil"));
        assertFalse(query.containsKey("brand"), "空值不转发");
    }

    @Test
    void everyEndpointRequiresAFridayReportPermission()
    {
        for (Method method : EbayFridayReportController.class.getDeclaredMethods())
        {
            boolean endpoint = Arrays.stream(method.getAnnotations()).anyMatch(a ->
                    a.annotationType().getPackageName().equals("org.springframework.web.bind.annotation"));
            if (!endpoint) continue;
            PreAuthorize permission = method.getAnnotation(PreAuthorize.class);
            assertTrue(permission != null && permission.value().contains("operations:ebayFridayReport:"), method.getName());
        }
    }

    @Test
    void orderUploadForwardsTheMultipartFileToPython()
    {
        EbayFridayReportPythonClient client = mock(EbayFridayReportPythonClient.class);
        MockMultipartFile file = new MockMultipartFile("file", "订单.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", new byte[] { 1, 2, 3 });
        when(client.importOrderSales(same(file), any(), any())).thenReturn(Map.of("data", Map.of("used_rows", 1713)));
        AjaxResult result = new EbayFridayReportController(client).importOrderSales(file, "req-1");
        assertEquals(200, result.get("code"));
        verify(client).importOrderSales(same(file), any(), eq("req-1"));
    }
}
