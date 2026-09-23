package com.ruoyi.web.task;
import com.ruoyi.system.service.finance.PerformancePythonClient;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.quartz.CronExpression;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
class HomeInventorySkuTaskTest
{
    @AfterEach void clear(){OperationSyncContext.clear();}
    @Test void successfulCaptureRecordsQuartzSummaryEvenWhenSkuCountIsZero()
    {
        var client=mock(PerformancePythonClient.class);
        when(client.captureHomeProductNature(anyString())).thenReturn(Map.of("data",Map.of("stat_month","2026-09","total",0,"captured_at","2026-09-30")));
        new HomeInventorySkuTask(client).captureMonthly();
        assertEquals(OperationSyncResult.STATUS_SUCCESS,OperationSyncContext.get().getStatus());
        assertTrue(OperationSyncContext.get().toJobMessage(null).contains("2026-09"));
    }
    @Test void captureFailurePropagatesToQuartz()
    {
        var client=mock(PerformancePythonClient.class);
        when(client.captureHomeProductNature(anyString())).thenThrow(new IllegalStateException("not ready"));
        assertThrows(IllegalStateException.class,()->new HomeInventorySkuTask(client).captureMonthly());
        assertNull(OperationSyncContext.get());
    }
    @Test void cronUsesRealLastDayIncludingLeapYear() throws Exception
    {
        var cron=new CronExpression("0 50 23 L * ?");
        cron.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
        for(var pair:List.of(new String[]{"2026-09-01T00:00:00Z","2026-09-30T15:50:00Z"},new String[]{"2028-02-01T00:00:00Z","2028-02-29T15:50:00Z"}))
            assertEquals(Instant.parse(pair[1]),cron.getNextValidTimeAfter(Date.from(Instant.parse(pair[0]))).toInstant());
    }
}
