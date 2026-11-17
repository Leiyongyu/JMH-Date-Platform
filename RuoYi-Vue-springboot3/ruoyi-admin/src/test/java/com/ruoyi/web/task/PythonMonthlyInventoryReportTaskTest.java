package com.ruoyi.web.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PythonMonthlyInventoryReportTaskTest
{
    @Test void salesSnapshotRefreshLogsRefreshOutcome()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runInventoryReportSalesSnapshotRefresh(isNull(), anyString()))
                .thenReturn(Map.of("data", Map.of("result", Map.of(
                        "report_refresh", Map.of(
                                "report_month", "2026-10",
                                "stat_month", "2026-09",
                                "status", "refreshed",
                                "changed_rows", 12)))));
        new PythonMonthlyInventoryReportTask(client, logs, new ObjectMapper())
                .refreshPreviousMonthSalesSnapshot();
        verify(client).runInventoryReportSalesSnapshotRefresh(
                isNull(), startsWith("quartz-monthly-inventory-report-"));
        var captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(), captor.capture());
        String summary = captor.getValue().getBusinessSummary();
        assertTrue(summary.contains("快照月份2026-09"), summary);
        assertTrue(summary.contains("回填结果refreshed"), summary);
        assertTrue(summary.contains("变更12行"), summary);
    }

    private static OperationSyncResult runWithRefresh(Map<String, Object> refresh)
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runInventoryReportSalesSnapshotRefresh(isNull(), anyString()))
                .thenReturn(Map.of("data", Map.of("status", "completed",
                        "result", Map.of("report_refresh", refresh))));
        try
        {
            new PythonMonthlyInventoryReportTask(client, logs, new ObjectMapper())
                    .refreshPreviousMonthSalesSnapshot();
        }
        catch (IllegalStateException ignored)
        {
            // failure path is asserted through the logged result
        }
        var captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(), captor.capture());
        return captor.getValue();
    }

    @Test void upToDateSnapshotWithZeroChangedRowsIsSuccessNotEmptyResultAlarm()
    {
        var result = runWithRefresh(Map.of("report_month", "2026-10", "stat_month", "2026-09",
                "status", "unchanged", "changed_rows", 0));
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertNull(result.getErrorMessage());
        assertTrue(result.getBusinessSummary().contains("回填结果unchanged"));
    }

    @Test void lockedOrMissingSnapshotIsLoggedAsSuccessWithReason()
    {
        for (String status : new String[] {"locked", "no_snapshot", "skipped"})
        {
            var result = runWithRefresh(Map.of("status", status, "changed_rows", 0,
                    "reason", "原因-" + status));
            assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus(), status);
            assertTrue(result.getBusinessSummary().contains("原因-" + status), status);
        }
    }

    @Test void explicitRefreshFailureOrMissingResultAlarms()
    {
        var failed = runWithRefresh(Map.of("status", "failed", "changed_rows", 0, "reason", "数据库超时"));
        assertEquals(OperationSyncResult.STATUS_FAILED, failed.getStatus());
        assertTrue(failed.getErrorMessage().contains("数据库超时"), failed.getErrorMessage());
        var missing = runWithRefresh(Map.of());
        assertEquals(OperationSyncResult.STATUS_FAILED, missing.getStatus());
        assertTrue(missing.getErrorMessage().contains("Python未返回回填结果"), missing.getErrorMessage());
    }

    @Test void salesSnapshotRefreshFailureIsPropagatedToQuartz()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runInventoryReportSalesSnapshotRefresh(any(), anyString()))
                .thenThrow(new IllegalStateException("locked"));
        assertThrows(IllegalStateException.class, () ->
                new PythonMonthlyInventoryReportTask(client, logs, new ObjectMapper())
                        .refreshSalesSnapshotMonth("2026-10"));
        verify(logs).finish(any(), any(OperationSyncResult.class));
    }
}
