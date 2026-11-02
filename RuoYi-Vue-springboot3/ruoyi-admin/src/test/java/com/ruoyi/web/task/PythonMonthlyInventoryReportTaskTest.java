package com.ruoyi.web.task;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
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
