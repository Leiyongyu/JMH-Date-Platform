package com.ruoyi.web.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class PythonOwnerRuleFeishuTaskTest
{
    private OperationSyncResult run(Map<String, Object> result)
    {
        PythonPerformanceSchedulerClient client = mock(PythonPerformanceSchedulerClient.class);
        IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), any(), any())).thenReturn(9L);
        when(client.runOwnerRuleFeishu(anyString())).thenReturn(Map.of("data", Map.of("result", result)));
        new PythonOwnerRuleFeishuTask(client, logs).runWeekly();
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(eq(9L), captor.capture());
        return captor.getValue();
    }

    @Test
    void unchangedContentIsASuccessNotAnEmptyFailure()
    {
        OperationSyncResult result = run(Map.of("status", "unchanged", "fetched_rows", 229, "imported_rows", 0));
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("飞书内容与上次相同"), result.getBusinessSummary());
    }

    @Test
    void importedRulesAreSummarised()
    {
        OperationSyncResult result = run(Map.of("status", "completed", "fetched_rows", 229, "imported_rows", 2712,
                "changed_months", List.of("2026-11"), "refreshed_months", List.of()));
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("负责人有变化的月份=[2026-11]"), result.getBusinessSummary());
    }

    @Test
    void failuresAreLoggedAndRethrown()
    {
        PythonPerformanceSchedulerClient client = mock(PythonPerformanceSchedulerClient.class);
        IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
        when(client.runOwnerRuleFeishu(anyString())).thenThrow(new IllegalStateException("飞书负责人表缺少数据表：EBAY"));
        assertThrows(IllegalStateException.class, () -> new PythonOwnerRuleFeishuTask(client, logs).runWeekly());
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(), captor.capture());
        assertEquals(OperationSyncResult.STATUS_FAILED, captor.getValue().getStatus());
    }
}
