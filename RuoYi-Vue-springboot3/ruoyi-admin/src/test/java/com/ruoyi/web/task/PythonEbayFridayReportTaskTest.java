package com.ruoyi.web.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class PythonEbayFridayReportTaskTest
{
    private final PythonPerformanceSchedulerClient scheduler = mock(PythonPerformanceSchedulerClient.class);
    private final IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
    private final SyncAlertService alerts = mock(SyncAlertService.class);

    private static Map<String, Object> result(Map<String, Object> details)
    {
        return Map.of("data", Map.of("result", details));
    }

    private OperationSyncResult finished()
    {
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(eq(5L), captor.capture());
        return captor.getValue();
    }

    @Test
    void pullsListingThenGoodcangThenGeneratesTheReport()
    {
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), any(), any())).thenReturn(5L);
        when(scheduler.runEbayStoreListing(anyString())).thenReturn(result(Map.of("ods_rows", 17457)));
        when(scheduler.runGoodcangProductInventory(anyString())).thenReturn(result(Map.of("ods_rows", 8258)));
        when(scheduler.runEbayFridayReport(anyString())).thenReturn(result(Map.of("report_date", "2026-11-13",
                "listing_count", 17457, "site_mismatch", 1121, "online_without_stock", 455, "stock_rows", 1386,
                "stock_no_link", 195, "extract_rows", 18843, "ods_rows", 18843)));
        new PythonEbayFridayReportTask(scheduler, logs, alerts).runWeekly();
        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("报表日期=2026-11-13"), result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("站点不符=1121"), result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("谷仓库存同步成功"), result.getBusinessSummary());
    }

    @Test
    void goodcangFailureAlertsButStillGenerates()
    {
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), any(), any())).thenReturn(5L);
        when(scheduler.runEbayStoreListing(anyString())).thenReturn(result(Map.of("ods_rows", 100)));
        when(scheduler.runGoodcangProductInventory(anyString())).thenThrow(new IllegalStateException("谷仓 HTTP 502"));
        when(scheduler.runEbayFridayReport(anyString())).thenReturn(result(Map.of("report_date", "2026-11-13",
                "extract_rows", 10, "ods_rows", 10)));
        new PythonEbayFridayReportTask(scheduler, logs, alerts).runWeekly();
        assertTrue(finished().getBusinessSummary().contains("本次谷仓未更新"));
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_friday_report_weekly:goodcang"), anyString(), anyString(),
                eq("FAILED"), anyString(), any());
    }

    @Test
    void emptyListingFailsWithoutGenerating()
    {
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), any(), any())).thenReturn(5L);
        when(scheduler.runEbayStoreListing(anyString())).thenReturn(result(Map.of("ods_rows", 0)));
        assertThrows(IllegalStateException.class, () -> new PythonEbayFridayReportTask(scheduler, logs, alerts).runWeekly());
        assertEquals(OperationSyncResult.STATUS_FAILED, finished().getStatus());
        verify(scheduler, never()).runEbayFridayReport(anyString());
    }
}
