package com.ruoyi.web.controller.finance;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.ruoyi.system.service.finance.ProjectProfitPythonClient;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.multipart.MultipartFile;

class ProjectProfitControllerTest
{
    private static ProjectProfitController controller(ProjectProfitPythonClient client)
    {
        return new ProjectProfitController(client)
        {
            @Override protected String operator() { return "admin"; }
        };
    }

    @Test
    void reportForwardsMonthAndRejectsBadMonthWithoutCallingPython()
    {
        var client = mock(ProjectProfitPythonClient.class);
        when(client.report("2026-09", "trace")).thenReturn(Map.of("data", Map.of("stat_month", "2026-09")));
        var response = controller(client).report(" 2026-09 ", "trace");
        assertEquals(200, response.get("code"));
        assertEquals(Map.of("stat_month", "2026-09"), response.get("data"));
        assertEquals(500, controller(client).report("2026-13", "trace").get("code"));
        verify(client, times(1)).report(anyString(), any());
    }

    @Test
    void saveItemsForwardsOnlyContractFieldsAndTakesOperatorFromLogin()
    {
        var client = mock(ProjectProfitPythonClient.class);
        when(client.saveItems(anyMap(), any())).thenReturn(Map.of("data", Map.of("saved", 1)));
        Map<String, Object> body = Map.of("statMonth", "2026-09", "operator", "hacker",
                "items", List.of(Map.of("groupCode", "EU", "itemCode", "labor_cost", "amount", -100, "x", 1)));
        assertEquals(200, controller(client).saveItems(body, "trace").get("code"));
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        verify(client).saveItems(captor.capture(), eq("trace"));
        Map<String, Object> sent = captor.getValue();
        assertEquals(List.of("stat_month", "items", "operator"), List.copyOf(sent.keySet()));
        assertEquals("admin", sent.get("operator"), "操作人取当前登录用户，不信任前端");
        @SuppressWarnings("unchecked")
        Map<String, Object> item = ((List<Map<String, Object>>) sent.get("items")).get(0);
        assertEquals(List.of("group_code", "item_code", "amount"), List.copyOf(item.keySet()));
        assertEquals(500, controller(client).saveItems(Map.of("statMonth", "2026-09", "items", List.of()), "t")
                .get("code"));
    }

    @Test
    void ebayUploadForwardsTheMultipartFileMonthAndOperator()
    {
        var client = mock(ProjectProfitPythonClient.class);
        MockMultipartFile file = new MockMultipartFile("file", "利润明细表202610-ebay.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", new byte[] { 1, 2, 3 });
        when(client.importEbay(same(file), eq("2026-10"), eq("admin"), any()))
                .thenReturn(Map.of("data", Map.of("stat_month", "2026-10")));
        assertEquals(200, controller(client).importEbay(file, "2026-10", "req-1").get("code"));
        verify(client).importEbay(same(file), eq("2026-10"), eq("admin"), eq("req-1"));
        assertEquals(500, controller(client).importEbay(file, "202610", "req-1").get("code"));
        verify(client, times(1)).importEbay(any(), any(), any(), any());
    }

    @Test
    void amzUploadPassesTheLoginUserAndRejectsBadMonth()
    {
        var client = mock(ProjectProfitPythonClient.class);
        MockMultipartFile file = new MockMultipartFile("file", "利润报表-MSKU.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", new byte[] { 1, 2, 3 });
        when(client.importAmz(same(file), eq("2026-09"), eq("admin"), any()))
                .thenReturn(Map.of("data", Map.of("stat_month", "2026-09")));
        assertEquals(200, controller(client).importAmz(file, "2026-09", "req-2").get("code"));
        verify(client).importAmz(same(file), eq("2026-09"), eq("admin"), eq("req-2"));
        assertEquals(500, controller(client).importAmz(file, "2026-9", "req-2").get("code"));
        verify(client, times(1)).importAmz(any(), any(), any(), any());
    }

    @Test
    void failuresAreReturnedAsErrors()
    {
        var client = mock(ProjectProfitPythonClient.class);
        when(client.report(anyString(), any())).thenThrow(new IllegalStateException("数据表不存在"));
        var response = controller(client).report("2026-09", null);
        assertEquals(500, response.get("code"));
        assertEquals("数据表不存在", response.get("msg"));
    }

    @Test
    void permissionsSeparateViewExportAndEdit() throws Exception
    {
        Class<?> type = ProjectProfitController.class;
        assertEquals("@ss.hasPermi('finance:projectProfit:list')",
                type.getMethod("report", String.class, String.class).getAnnotation(PreAuthorize.class).value());
        assertEquals("@ss.hasPermi('finance:projectProfit:edit')",
                type.getMethod("saveItems", Map.class, String.class).getAnnotation(PreAuthorize.class).value());
        assertEquals("@ss.hasPermi('finance:projectProfit:edit')",
                type.getMethod("importEbay", MultipartFile.class, String.class, String.class)
                        .getAnnotation(PreAuthorize.class).value());
        assertEquals("@ss.hasPermi('finance:projectProfit:edit')",
                type.getMethod("importAmz", MultipartFile.class, String.class, String.class)
                        .getAnnotation(PreAuthorize.class).value());
        assertTrue(type.getMethod("export", String.class, String.class).getAnnotation(PreAuthorize.class).value()
                .contains("finance:projectProfit:export"));
    }
}
