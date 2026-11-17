package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PythonAmzProfitReportTaskTest
{
    private static Map<String, Object> ok(String month)
    {
        return Map.of("data", Map.of("result", Map.of(
                "stat_month", month, "extract_rows", 3, "ods_rows", 3,
                "seller_rows", 1, "msku_rows", 1, "order_rows", 1, "sync_batch_id", "b")));
    }

    @Test void monthRangePullsEachMonthInOrder()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runAmzProfitReport(anyString(), anyString()))
                .thenAnswer(call -> ok(call.getArgument(0)));

        new PythonAmzProfitReportTask(client, logs).syncMonthRange("2026-07", "2026-09");

        InOrder order = inOrder(client);
        order.verify(client).runAmzProfitReport(eq("2026-07"), startsWith("quartz-amz-profit-report-"));
        order.verify(client).runAmzProfitReport(eq("2026-08"), anyString());
        order.verify(client).runAmzProfitReport(eq("2026-09"), anyString());
        verify(logs, times(3)).finish(any(), any(OperationSyncResult.class));
    }

    @Test void failedMonthDoesNotStopLaterMonthsAndIsReported()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runAmzProfitReport(anyString(), anyString()))
                .thenAnswer(call -> ok(call.getArgument(0)));
        when(client.runAmzProfitReport(eq("2026-08"), anyString()))
                .thenThrow(new IllegalStateException("领星返回500"));

        var error = assertThrows(IllegalStateException.class, () ->
                new PythonAmzProfitReportTask(client, logs).syncMonthRange("2026-07", "2026-09"));

        verify(client).runAmzProfitReport(eq("2026-09"), anyString());
        assertTrue(error.getMessage().contains("2026-08"), error.getMessage());
    }

    @Test void invalidRangesAreRejectedBeforeAnyPull()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var task = new PythonAmzProfitReportTask(client, mock(IOperationSyncLogService.class));
        assertThrows(IllegalArgumentException.class, () -> task.syncMonthRange("2026-09", "2026-07"));
        assertThrows(IllegalArgumentException.class, () -> task.syncMonthRange("2025-01", "2026-09"));
        verifyNoInteractions(client);
    }
}
