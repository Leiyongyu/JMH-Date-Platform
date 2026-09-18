package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PythonAmzListingRawTaskTest
{
    @Test void forwardsToIsolatedPythonTaskAndFinishesLog()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runAmzListingRaw(anyString())).thenReturn(Map.of("data", Map.of("result",
                Map.of("extract_rows", 2, "ods_rows", 2, "shop_count", 1, "sync_batch_id", "batch"))));
        new PythonAmzListingRawTask(client, logs).runWeekly();
        verify(client).runAmzListingRaw(startsWith("quartz-amz-listing-raw-"));
        verifyNoMoreInteractions(client);
        verify(logs).finish(any(), any(OperationSyncResult.class));
    }

    @Test void failureIsRecordedAndPropagatedToQuartz()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        when(client.runAmzListingRaw(anyString())).thenThrow(new IllegalStateException("safe error"));
        assertThrows(IllegalStateException.class, () -> new PythonAmzListingRawTask(client, logs).runWeekly());
        verify(logs).finish(any(), any(OperationSyncResult.class));
    }
}
