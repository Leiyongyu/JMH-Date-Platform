package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.operation.ebay.EbayInventoryDetailPythonClient;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EbayInventoryDetailMultiFilterControllerTest
{
    @Test
    void exportForwardsDateRangeWithoutRowFilters() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.export(anyMap(), any())).thenReturn(new EbayInventoryDetailPythonClient.ExcelFile(
                new byte[] {80, 75}, "attachment; filename=test.xlsx"));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        mvc.perform(post("/finance/ebay-inventory-detail/export").contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"startDate":"2026-09-01","endDate":"2026-09-29","site":"英国"}
                                """))
                .andExpect(status().isOk());
        verify(client).export(argThat(payload -> "2026-09-01".equals(payload.get("start_date"))
                && "2026-09-29".equals(payload.get("end_date")) && !payload.containsKey("site")), isNull());
    }

    @Test
    void listForwardsCsvAsStringsWithoutLosingLeadingZeros() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.list(anyMap(), any())).thenReturn(Map.of("data", Map.of()));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        mvc.perform(get("/finance/ebay-inventory-detail/list")
                        .param("sku", "10053,00123").param("brand", "DAS,MCD").param("grade", "A,S")
                        .param("statDate", "2026-09-16").param("pageNum", "2"))
                .andExpect(status().isOk());
        verify(client).list(argThat(params -> "10053,00123".equals(params.get("sku"))
                && "DAS,MCD".equals(params.get("brand")) && "A,S".equals(params.get("grade"))
                && "2026-09-16".equals(params.get("stat_date")) && Integer.valueOf(2).equals(params.get("page"))), isNull());
    }

    @Test
    void exportIgnoresFiltersSelectionAndPaginationButKeepsSnapshotAndSorting() throws Exception
    {
        var client = mock(EbayInventoryDetailPythonClient.class);
        when(client.export(anyMap(), any())).thenReturn(new EbayInventoryDetailPythonClient.ExcelFile(
                new byte[] {80, 75}, "attachment; filename=test.xlsx"));
        var mvc = MockMvcBuilders.standaloneSetup(new EbayInventoryDetailController(client)).build();
        mvc.perform(post("/finance/ebay-inventory-detail/export").contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"site":"英国","sku":"10053,00123","brand":"DAS,MCD","grade":"A,S",
                                 "statDate":"2026-09-16","sortField":"sku","sortOrder":"ascending",
                                 "pageNum":2,"pageSize":1,"selectedKeys":[{"site":"英国","sku":"SKU-B"}]}
                                """))
                .andExpect(status().isOk());
        verify(client).export(eq(Map.of("stat_date", "2026-09-16",
                "sort_field", "sku", "sort_order", "ascending")), isNull());
    }
}
