package com.ruoyi.web.controller.finance;

import com.ruoyi.system.service.finance.PerformancePythonClient;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 排名列表的未分配排除开关，以及未匹配排查端点的参数透传。 */
class PerformanceRankingUnmatchedControllerTest
{
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void listForwardsExcludeUnassignedFlag() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.rankings(anyMap(), any())).thenReturn(Map.of(
                "data", Map.of(
                        "items", List.of(Map.of("principalNames", "张三")),
                        "pagination", Map.of("total", 1),
                        "stat_month", "2026-10",
                        "currency", "CNY")));
        var mvc = MockMvcBuilders
                .standaloneSetup(new PerformanceRankingController(client)).build();

        mvc.perform(get("/finance/performance-ranking/list")
                        .param("platform", "combined")
                        .param("statMonth", "2026-10")
                        .param("excludeUnassigned", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));

        var expected = new LinkedHashMap<String, Object>();
        expected.put("platform", "combined");
        expected.put("stat_month", "2026-10");
        expected.put("principal_name", null);
        expected.put("order_by", "gross_profit");
        expected.put("order", "desc");
        expected.put("page", 1);
        expected.put("page_size", 100);
        expected.put("exclude_unassigned", true);
        verify(client).rankings(expected, null);
    }

    @Test void listKeepsUnassignedWhenFlagIsAbsent() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.rankings(anyMap(), any())).thenReturn(Map.of("data", Map.of()));
        var mvc = MockMvcBuilders
                .standaloneSetup(new PerformanceRankingController(client)).build();

        mvc.perform(get("/finance/performance-ranking/list"))
                .andExpect(status().isOk());

        // Default must stay false: the AI assistant and the monthly inventory
        // report still read the 未分配 row through this same endpoint.
        verify(client).rankings(argThat(params ->
                Boolean.FALSE.equals(params.get("exclude_unassigned"))), isNull());
    }

    @Test void unmatchedForwardsPlatformAndMonth() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.rankingUnmatched(anyMap(), any())).thenReturn(Map.of(
                "data", Map.of(
                        "stat_month", "2026-10",
                        "items", List.of(Map.of(
                                "reason", "RULE_MISSING",
                                "matchKey", "新店")),
                        "totals", Map.of("keys", 1))));
        var mvc = MockMvcBuilders
                .standaloneSetup(new PerformanceRankingController(client)).build();

        mvc.perform(get("/finance/performance-ranking/unmatched")
                        .param("platform", "amazon")
                        .param("statMonth", "2026-10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.items[0].reason").value("RULE_MISSING"))
                .andExpect(jsonPath("$.data.totals.keys").value(1));

        var expected = new LinkedHashMap<String, Object>();
        expected.put("platform", "amazon");
        expected.put("stat_month", "2026-10");
        verify(client).rankingUnmatched(expected, null);
    }

    @Test void unmatchedReportsPythonFailureAsError() throws Exception
    {
        var client = mock(PerformancePythonClient.class);
        when(client.rankingUnmatched(anyMap(), any()))
                .thenThrow(new IllegalStateException("Python绩效服务不可用"));
        var mvc = MockMvcBuilders
                .standaloneSetup(new PerformanceRankingController(client)).build();

        mvc.perform(get("/finance/performance-ranking/unmatched"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.msg").value("Python绩效服务不可用"));
    }
}
