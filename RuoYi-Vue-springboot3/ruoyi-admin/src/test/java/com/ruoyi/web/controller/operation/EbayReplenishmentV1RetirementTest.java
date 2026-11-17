package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2ExportService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2LeadTimeService;
import com.ruoyi.system.service.operation.ebay.EbayReplenishmentV2PythonClient;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * eBay补货1.0、每日跟价、品牌负责人、链接模版均已下线：
 * 旧路由不再存在，补货2.0 的列表与刷新照常转发到 Python。
 */
class EbayReplenishmentV1RetirementTest
{
    private MockMvc mvc;
    private EbayReplenishmentV2PythonClient client;

    @BeforeEach
    void setup()
    {
        client = mock(EbayReplenishmentV2PythonClient.class);
        var v2 = new EbayReplenishmentV2Controller(client,
                mock(EbayReplenishmentV2LeadTimeService.class), new EbayReplenishmentV2ExportService());
        mvc = MockMvcBuilders.standaloneSetup(v2).build();
    }

    @Test
    void retiredEndpointsAreAbsentWhileV2ListAndRefreshStillReachPython() throws Exception
    {
        for (String path : List.of("list", "distinct-values", "formula/list"))
            mvc.perform(get("/operations/ebay/replenishment/" + path)).andExpect(status().isNotFound());
        for (String path : List.of("search", "refresh", "export", "update-product-nature", "formula/update"))
            mvc.perform(post("/operations/ebay/replenishment/" + path)).andExpect(status().isNotFound());
        for (String path : List.of("search", "refresh", "export", "import-sales", "link-template"))
            mvc.perform(post("/operations/ebay/price-tracking/" + path)).andExpect(status().isNotFound());
        mvc.perform(get("/operations/brand-owner/list")).andExpect(status().isNotFound());
        when(client.list(anyMap(), any())).thenReturn(Map.of("data", Map.of("items", List.of(), "total", 0)));
        mvc.perform(get("/operations/ebay/replenishment-v2/list"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
        mvc.perform(get("/operations/ebay/replenishment-v2/list").param("refresh", "true"))
                .andExpect(status().isOk());
        verify(client).list(argThat(params -> Boolean.TRUE.equals(params.get("refresh"))), any());
    }
}
