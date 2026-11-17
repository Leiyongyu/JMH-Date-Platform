package com.ruoyi.web.controller.operation;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.web.task.PythonEbayMixedSalesPriceTask;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MixedSalesPriceTaskTest
{
    @AfterEach void clear() { OperationSyncContext.clear(); }

    @Test
    void successfulPublishRecordsMonthStoreCountAndSkippedAuthorizationRows()
    {
        var client=mock(PythonPerformanceSchedulerClient.class);
        var logs=mock(IOperationSyncLogService.class);
        when(client.runEbayMixedSalesPrices(any())).thenReturn(Map.of("data",Map.of("result",Map.of(
            "extract_rows",12,"shop_count",2,"stat_month","2026-10","skipped_rows",1))));
        new PythonEbayMixedSalesPriceTask(client,logs).runMonthly();
        ArgumentCaptor<OperationSyncResult> result=ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(),result.capture());
        assertTrue(result.getValue().getBusinessSummary().contains("2026-10"));
        assertTrue(result.getValue().getBusinessSummary().contains("缺授权跳过=1"));
    }

    @Test
    void failuresDoNotLeakRawClientExceptionIntoJobLog()
    {
        var client=mock(PythonPerformanceSchedulerClient.class);
        var logs=mock(IOperationSyncLogService.class);
        when(client.runEbayMixedSalesPrices(any())).thenThrow(new IllegalStateException("sensitive-token"));
        var error=assertThrows(IllegalStateException.class,()->new PythonEbayMixedSalesPriceTask(client,logs).runMonthly());
        assertFalse(error.getMessage().contains("sensitive-token"));
        ArgumentCaptor<OperationSyncResult> result=ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(),result.capture());
        assertFalse(result.getValue().getErrorMessage().contains("sensitive-token"));
    }
}
