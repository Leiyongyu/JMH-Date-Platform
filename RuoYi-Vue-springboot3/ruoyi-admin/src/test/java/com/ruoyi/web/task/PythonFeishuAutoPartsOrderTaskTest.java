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
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class PythonFeishuAutoPartsOrderTaskTest
{
    @Test
    void successIsSummarisedWithEbayOpenOrders()
    {
        PythonPerformanceSchedulerClient client = mock(PythonPerformanceSchedulerClient.class);
        IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
        when(logs.start(anyString(), anyString(), anyString(), anyString(), anyString(), any(), any())).thenReturn(7L);
        when(client.runFeishuAutoPartsOrder(anyString())).thenReturn(Map.of("data", Map.of("result", Map.of(
                "fetched_rows", 857, "inserted_rows", 857, "ebay_rows", 285, "ebay_open_rows", 282))));
        new PythonFeishuAutoPartsOrderTask(client, logs).run();
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(eq(7L), captor.capture());
        OperationSyncResult result = captor.getValue();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, result.getStatus());
        assertTrue(result.getBusinessSummary().contains("eBay仓=285"), result.getBusinessSummary());
        assertTrue(result.getBusinessSummary().contains("认出站点=282"), result.getBusinessSummary());
    }

    @Test
    void failuresAreLoggedAndRethrown()
    {
        PythonPerformanceSchedulerClient client = mock(PythonPerformanceSchedulerClient.class);
        IOperationSyncLogService logs = mock(IOperationSyncLogService.class);
        when(client.runFeishuAutoPartsOrder(anyString())).thenThrow(new IllegalStateException("飞书汽配订单返回0行"));
        assertThrows(IllegalStateException.class, () -> new PythonFeishuAutoPartsOrderTask(client, logs).run());
        ArgumentCaptor<OperationSyncResult> captor = ArgumentCaptor.forClass(OperationSyncResult.class);
        verify(logs).finish(any(), captor.capture());
        assertEquals(OperationSyncResult.STATUS_FAILED, captor.getValue().getStatus());
    }
}
