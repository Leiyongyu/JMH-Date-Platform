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

class PythonEbayMonthlyProfitTaskTest
{
    @Test
    void goodcangBillPullIsSummarised()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), any(), any())).thenReturn(5L);
        when(client.runGoodcangBill(isNull(), anyString())).thenReturn(Map.of("data", Map.of("result", Map.of(
                "stat_month", "2026-10", "extract_rows", 29873, "ods_rows", 29873,
                "bills", List.of("B20261015G106450002", "B20261101G106450002"),
                "pulled_at", "2026-11-07 05:00:00", "sync_batch_id", "b"))));

        new PythonEbayMonthlyProfitTask(client, logs).syncGoodcangBillPreviousMonth();

        verify(client).runGoodcangBill(isNull(), startsWith("quartz-goodcang-bill-monthly-sync-"));
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(eq(5L), captor.capture());
        assertEquals(OperationSyncResult.STATUS_SUCCESS, captor.getValue().getStatus());
        String summary = captor.getValue().getBusinessSummary();
        assertTrue(summary.contains("月份2026-10") && summary.contains("费用行=29873")
                && summary.contains("B20261101G106450002"), summary);
    }

    @Test
    void ebayFinancePullCountsFailedStores()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runEbayFinance(eq("2026-10"), anyString())).thenReturn(Map.of("data", Map.of("result", Map.of(
                "stat_month", "2026-10", "extract_rows", 33886, "ods_rows", 33886, "store_count", 36,
                "failed_stores", Map.of("Global Auto Store", "TOKEN_INVALID"), "missing_sku_rows", 3,
                "pulled_at", "2026-11-07 05:30:00", "sync_batch_id", "b"))));

        new PythonEbayMonthlyProfitTask(client, logs).syncEbayFinanceMonth(" 2026-10 ");

        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(), captor.capture());
        String summary = captor.getValue().getBusinessSummary();
        assertTrue(summary.contains("店铺=36") && summary.contains("失败店铺=1") && summary.contains("交易行=33886"), summary);
    }

    @Test
    void failureIsLoggedAndRethrown()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runEbayFinance(isNull(), anyString())).thenThrow(new IllegalStateException("eBay 超时"));

        var error = assertThrows(IllegalStateException.class,
                () -> new PythonEbayMonthlyProfitTask(client, logs).syncEbayFinancePreviousMonth());

        assertTrue(error.getMessage().contains("eBay月度利润表-交易流水拉取失败"));
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(), captor.capture());
        assertEquals(OperationSyncResult.STATUS_FAILED, captor.getValue().getStatus());
    }
}
