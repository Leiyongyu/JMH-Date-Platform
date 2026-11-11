package com.ruoyi.web.controller.finance;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.ruoyi.system.service.finance.AmzMonthlyProfitPythonClient;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.access.prepost.PreAuthorize;

class AmzMonthlyProfitControllerTest
{
    private static AmzMonthlyProfitController controller(AmzMonthlyProfitPythonClient client)
    {
        return new AmzMonthlyProfitController(client)
        {
            @Override protected String operator() { return "admin"; }
        };
    }

    @Test
    void reportForwardsMonthAndRejectsBadMonthWithoutCallingPython()
    {
        var client = mock(AmzMonthlyProfitPythonClient.class);
        when(client.report("2026-09", "trace")).thenReturn(Map.of("data", Map.of("stat_month", "2026-09")));
        var response = controller(client).report(" 2026-09 ", "trace");
        assertEquals(200, response.get("code"));
        assertEquals(Map.of("stat_month", "2026-09"), response.get("data"));
        assertEquals(500, controller(client).report("2026-13", "trace").get("code"));
        verify(client, times(1)).report(anyString(), any());
    }

    @Test
    void createAdjustmentForwardsOnlyContractFieldsAndTakesOperatorFromLogin()
    {
        var client = mock(AmzMonthlyProfitPythonClient.class);
        when(client.createAdjustment(anyMap(), any())).thenReturn(Map.of("data", Map.of("id", 7)));
        Map<String, Object> body = new HashMap<>(Map.of("statMonth", "2026-09", "rowCode", "MJ",
                "feeItem", "warehouse_fee", "amount", -100, "remark", "r", "operator", "hacker", "extra", "x"));
        var response = controller(client).createAdjustment(body, "trace");
        assertEquals(200, response.get("code"));
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        verify(client).createAdjustment(captor.capture(), eq("trace"));
        Map<String, Object> sent = captor.getValue();
        assertEquals(List.of("stat_month", "row_code", "fee_item", "amount", "remark", "operator"),
                List.copyOf(sent.keySet()));
        assertEquals("admin", sent.get("operator"), "操作人取当前登录用户，不信任前端");
        assertEquals("MJ", sent.get("row_code"));
    }

    @Test
    void failuresAreReturnedAsErrors()
    {
        var client = mock(AmzMonthlyProfitPythonClient.class);
        when(client.report(anyString(), any())).thenThrow(new IllegalStateException("2026-09 还没有拉取"));
        var response = controller(client).report("2026-09", null);
        assertEquals(500, response.get("code"));
        assertEquals("2026-09 还没有拉取", response.get("msg"));
    }

    @Test
    void permissionsSeparateViewExportAndEdit() throws Exception
    {
        Class<?> type = AmzMonthlyProfitController.class;
        assertEquals("@ss.hasPermi('finance:amzMonthlyProfit:list')",
                type.getMethod("report", String.class, String.class).getAnnotation(PreAuthorize.class).value());
        assertEquals("@ss.hasPermi('finance:amzMonthlyProfit:edit')",
                type.getMethod("createAdjustment", Map.class, String.class).getAnnotation(PreAuthorize.class).value());
        assertEquals("@ss.hasPermi('finance:amzMonthlyProfit:edit')",
                type.getMethod("deleteAdjustment", long.class, String.class).getAnnotation(PreAuthorize.class).value());
        assertTrue(type.getMethod("export", String.class, String.class).getAnnotation(PreAuthorize.class).value()
                .contains("finance:amzMonthlyProfit:export"));
    }

    @Test
    void exportReturnsTheWorkbookOrPlainTextError()
    {
        var client = mock(AmzMonthlyProfitPythonClient.class);
        when(client.export("2026-09", null)).thenReturn(new byte[] {1, 2, 3});
        var ok = controller(client).export("2026-09", null);
        assertEquals(200, ok.getStatusCode().value());
        assertTrue(ok.getHeaders().getFirst("Content-Disposition").contains("2026-09.xlsx"));
        when(client.export("2026-08", null)).thenThrow(new IllegalStateException("没有数据"));
        assertEquals(400, controller(client).export("2026-08", null).getStatusCode().value());
    }
}
