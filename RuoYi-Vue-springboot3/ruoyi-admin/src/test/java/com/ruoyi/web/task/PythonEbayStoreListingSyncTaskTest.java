package com.ruoyi.web.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.ebay.EbayPriceAnalysisPythonClient;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/** 日级任务里刷表遇到锁冲突(409)时的重试：重试一次，仍失败只告警，不推翻 listing。 */
class PythonEbayStoreListingSyncTaskTest
{
    private static final String CONFLICT =
            "Python绩效ETL错误[HTTP 409]: eBay在售售价同步正在执行";

    private final PythonPerformanceSchedulerClient scheduler = mock(PythonPerformanceSchedulerClient.class);
    private final IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
    private final SyncAlertService alerts = mock(SyncAlertService.class);
    private final PythonEbayStoreListingSyncTask task = new PythonEbayStoreListingSyncTask(
            scheduler, mock(EbayPriceAnalysisPythonClient.class), logs, alerts);

    PythonEbayStoreListingSyncTaskTest()
    {
        task.refreshRetryDelayMillis = 0;
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), isNull(), isNull()))
                .thenReturn(5L);
        when(scheduler.runEbayStoreListing(anyString())).thenReturn(Map.of("code", 0, "data",
                Map.of("status", "completed", "result",
                        Map.of("extract_rows", 18013, "ods_rows", 18013, "shop_count", 37))));
    }

    private static Map<String, Object> refreshed()
    {
        return Map.of("code", 0, "data", Map.of("status", "completed", "result",
                Map.of("rows", 18013, "matched_rows", 18000, "stat_date", "2026-11-10")));
    }

    private OperationSyncResult finished()
    {
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(eq(5L), captor.capture());
        return captor.getValue();
    }

    @Test
    void lockConflictIsRetriedOnceAndNotedInSummary()
    {
        when(scheduler.runEbayPriceAnalysisRefresh(anyString()))
                .thenThrow(new IllegalStateException(CONFLICT))
                .thenReturn(refreshed());

        task.runDaily();

        verify(scheduler, times(2)).runEbayPriceAnalysisRefresh(anyString());
        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("首次遇锁冲突(409)，重试后成功"), result.getBusinessSummary());
        verify(alerts, never()).sendAlert(anyString(), anyString(), anyString(), anyString(), anyString(),
                anyString(), any());
    }

    @Test
    void secondLockConflictAlertsButKeepsListingPull()
    {
        when(scheduler.runEbayPriceAnalysisRefresh(anyString()))
                .thenThrow(new IllegalStateException(CONFLICT));

        task.runDaily();

        verify(scheduler, times(2)).runEbayPriceAnalysisRefresh(anyString());
        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("重试仍失败"), result.getBusinessSummary());
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_daily_sync:refresh"), anyString(),
                anyString(), eq("FAILED"), contains("重试仍失败"), isNull());
    }

    @Test
    void conflictAfterRetryFailingOtherwiseStillAlerts()
    {
        when(scheduler.runEbayPriceAnalysisRefresh(anyString()))
                .thenThrow(new IllegalStateException(CONFLICT))
                .thenThrow(new IllegalStateException("Python绩效ETL错误[HTTP 502]: 内部任务执行失败: boom"));

        task.runDaily();

        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_daily_sync:refresh"), anyString(),
                anyString(), eq("FAILED"), contains("HTTP 502"), isNull());
    }

    @Test
    void recognisesConflictOnlyFromHttp409()
    {
        assertTrue(PythonEbayStoreListingSyncTask.isLockConflict(new IllegalStateException(CONFLICT)));
        assertTrue(PythonEbayStoreListingSyncTask.isLockConflict(
                new IllegalStateException("外层", new IllegalStateException(CONFLICT))));
        assertFalse(PythonEbayStoreListingSyncTask.isLockConflict(
                new IllegalStateException("Python绩效ETL错误[HTTP 502]: 409 行已写入")));
        assertFalse(PythonEbayStoreListingSyncTask.isLockConflict(new IllegalStateException((String) null)));
    }
}
