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
}
