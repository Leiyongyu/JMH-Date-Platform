package com.ruoyi.web.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.inOrder;
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

/**
 * 每周任务：listing → 谷仓库存 → 刷表。谷仓失败单独告警、继续刷表；
 * 刷表遇到锁冲突(409)时重试一次，仍失败只告警，不推翻 listing。
 */
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
        when(scheduler.runGoodcangProductInventory(anyString())).thenReturn(
                Map.of("code", 0, "data", Map.of("status", "completed", "result",
                        Map.of("extract_rows", 9120, "ods_rows", 9120, "sync_batch_id", "gc-1"))));
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

        task.runWeekly();

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

        task.runWeekly();

        verify(scheduler, times(2)).runEbayPriceAnalysisRefresh(anyString());
        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("重试仍失败"), result.getBusinessSummary());
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_weekly_sync:refresh"), anyString(),
                anyString(), eq("FAILED"), contains("重试仍失败"), isNull());
    }

    @Test
    void conflictAfterRetryFailingOtherwiseStillAlerts()
    {
        when(scheduler.runEbayPriceAnalysisRefresh(anyString()))
                .thenThrow(new IllegalStateException(CONFLICT))
                .thenThrow(new IllegalStateException("Python绩效ETL错误[HTTP 502]: 内部任务执行失败: boom"));

        task.runWeekly();

        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_weekly_sync:refresh"), anyString(),
                anyString(), eq("FAILED"), contains("HTTP 502"), isNull());
    }

    @Test
    void goodcangFailureAlertsSeparatelyKeepsListingAndStillRefreshes()
    {
        when(scheduler.runGoodcangProductInventory(anyString()))
                .thenThrow(new IllegalStateException("Python绩效ETL错误[HTTP 502]: 谷仓接口超时"));
        when(scheduler.runEbayPriceAnalysisRefresh(anyString())).thenReturn(refreshed());

        task.runWeekly();

        var order = inOrder(scheduler);
        order.verify(scheduler).runEbayStoreListing(anyString());
        order.verify(scheduler).runGoodcangProductInventory(anyString());
        order.verify(scheduler).runEbayPriceAnalysisRefresh(anyString());
        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertEquals(18013, result.getSuccessCount());
        assertTrue(result.getBusinessSummary().contains("本次谷仓未更新"), result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("价格分析刷表成功"), result.getBusinessSummary());
        // 告警码与刷表失败分开；刷表本身成功，不发刷表告警。
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_weekly_sync:goodcang"), anyString(),
                eq("/api/v1/internal/scheduler/tasks/goodcang_product_inventory_sync/run"),
                eq("FAILED"), contains("本次谷仓未更新"), isNull());
        verify(alerts, never()).sendAlert(anyString(), eq("ebay_price_analysis_weekly_sync:refresh"),
                anyString(), anyString(), anyString(), anyString(), any());
    }

    @Test
    void goodcangEmptyOrMissingResultIsTreatedAsNotUpdated()
    {
        when(scheduler.runGoodcangProductInventory(anyString())).thenReturn(Map.of("code", 0,
                "data", Map.of("status", "completed", "result", Map.of("ods_rows", 0))));
        when(scheduler.runEbayPriceAnalysisRefresh(anyString())).thenReturn(refreshed());

        task.runWeekly();

        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("本次谷仓未更新"), result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("空快照"), result.getBusinessSummary());
        verify(scheduler, times(1)).runEbayPriceAnalysisRefresh(anyString());
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_weekly_sync:goodcang"), anyString(),
                anyString(), eq("FAILED"), contains("空快照"), isNull());
    }

    @Test
    void goodcangAndRefreshBothFailingRaiseTwoDistinctAlerts()
    {
        when(scheduler.runGoodcangProductInventory(anyString()))
                .thenThrow(new IllegalStateException("谷仓 boom"));
        when(scheduler.runEbayPriceAnalysisRefresh(anyString()))
                .thenThrow(new IllegalStateException("Python绩效ETL错误[HTTP 502]: 刷表 boom"));

        task.runWeekly();

        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_weekly_sync:goodcang"), anyString(),
                anyString(), eq("FAILED"), contains("谷仓 boom"), isNull());
        verify(alerts).sendAlert(eq("ebay"), eq("ebay_price_analysis_weekly_sync:refresh"), anyString(),
                anyString(), eq("FAILED"), contains("刷表 boom"), isNull());
    }

    @Test
    @SuppressWarnings("deprecation")
    void legacyRunDailyEntryRunsTheSameThreeWeeklySteps()
    {
        when(scheduler.runEbayPriceAnalysisRefresh(anyString())).thenReturn(refreshed());

        task.runDaily();

        var order = inOrder(scheduler);
        order.verify(scheduler).runEbayStoreListing(anyString());
        order.verify(scheduler).runGoodcangProductInventory(anyString());
        order.verify(scheduler).runEbayPriceAnalysisRefresh(anyString());
        verify(logs).start(eq("ebay_price_analysis_weekly_sync"), anyString(), anyString(),
                anyString(), anyString(), isNull(), isNull());
        OperationSyncResult result = finished();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("谷仓库存同步成功"), result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("价格分析刷表成功"), result.getBusinessSummary());
    }

    @Test
    void staleAlertDefaultsToEightDaysForAWeeklySnapshot() throws Exception
    {
        var field = PythonEbayStoreListingSyncTask.class.getDeclaredField("maxSnapshotAgeDays");
        var value = field.getAnnotation(org.springframework.beans.factory.annotation.Value.class);
        assertEquals("${ebay.price-analysis.stale-alert.max-age-days:8}", value.value());
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
