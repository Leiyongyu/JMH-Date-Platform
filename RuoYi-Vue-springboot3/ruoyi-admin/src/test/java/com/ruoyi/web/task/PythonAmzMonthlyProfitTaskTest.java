package com.ruoyi.web.task;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class PythonAmzMonthlyProfitTaskTest
{
    @Test
    void previousMonthPullIsSummarised()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), any(), any())).thenReturn(5L);
        when(client.runAmzMonthlyProfit(isNull(), anyString())).thenReturn(Map.of("data", Map.of("result", Map.of(
                "stat_month", "2026-10", "extract_rows", 12517, "ods_rows", 12517, "msku_rows", 12418,
                "seller_rows", 99, "reconcile_diff_stores", List.of(), "transit_loss_total", "-7576.59",
                "pulled_at", "2026-11-07 06:00:00", "sync_batch_id", "b"))));

        new PythonAmzMonthlyProfitTask(client, logs).syncPreviousMonth();

        verify(client).runAmzMonthlyProfit(isNull(), startsWith("quartz-amz-monthly-profit-"));
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(eq(5L), captor.capture());
        assertEquals(OperationSyncResult.STATUS_SUCCESS, captor.getValue().getStatus());
        String summary = captor.getValue().getBusinessSummary();
        assertTrue(summary.contains("月份2026-10") && summary.contains("MSKU=12418")
                && summary.contains("不一致的店铺=0") && summary.contains("FBA途损合计=-7576.59"), summary);
    }

    @Test
    void monthIsForwardedAndFailureIsLoggedAndRethrown()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runAmzMonthlyProfit(eq("2026-09"), anyString())).thenThrow(new IllegalStateException("领星超时"));

        var error = assertThrows(IllegalStateException.class,
                () -> new PythonAmzMonthlyProfitTask(client, logs).syncMonth(" 2026-09 "));

        assertTrue(error.getMessage().contains("AMZ月度利润表数据拉取失败"));
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(), captor.capture());
        assertEquals(OperationSyncResult.STATUS_FAILED, captor.getValue().getStatus());
    }
}
