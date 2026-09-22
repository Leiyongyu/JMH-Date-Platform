package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.IOperationSyncLogService;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.quartz.CronExpression;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PythonEbayTokenHealthTaskTest
{
    private Map<String, Object> report(int n)
    {
        List<Map<String, Object>> accounts = new ArrayList<>();
        for (int i=0; i<n; i++) accounts.add(Map.of("source_row",i+2,"shop_name","中文店铺名称".repeat(12),
                "status","HEALTHY","listing_count",123,"previous_count",120,"expires_on","2028-03-18",
                "days_remaining",500,"reason","OK"));
        return Map.of("accounts",accounts,"summary",Map.of("HEALTHY",n),"sync_batch_id","test-batch",
                "checked_at","2026-09-30 09:00:00","skipped_rows",4,"extract_rows",n);
    }

    @Test void healthyReportAlwaysSentAndSplitByUtf8Bytes()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        var alerts = mock(SyncAlertService.class);
        var data = report(37);
        when(client.runEbayTokenHealth(anyString())).thenReturn(Map.of("data",Map.of("result",data)));
        when(alerts.sendCredentialReminder(anyString(),anyString())).thenReturn(true);
        new PythonEbayTokenHealthTask(client,logs,alerts).runMonthly();
        List<String> parts = PythonEbayTokenHealthTask.reportMessages(data);
        assertTrue(parts.size()>1);
        assertTrue(parts.stream().allMatch(x->x.getBytes(StandardCharsets.UTF_8).length<=3400));
        verify(alerts,times(parts.size())).sendCredentialReminder(startsWith("health:test-batch:"),anyString());
        assertTrue(String.join("",parts).contains("正常：37"));
        verify(logs).finish(any(),any());
    }

    @Test void notificationFailureIsTaskFailure()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var logs = mock(IOperationSyncLogService.class);
        var alerts = mock(SyncAlertService.class);
        when(client.runEbayTokenHealth(anyString())).thenReturn(Map.of("data",Map.of("result",report(1))));
        assertThrows(IllegalStateException.class,()->new PythonEbayTokenHealthTask(client,logs,alerts).runMonthly());
        verify(logs).finish(any(),any());
    }

    @Test void lastDayCronCoversFebruaryAndThirtyOneDayMonths() throws Exception
    {
        var cron = new CronExpression("0 0 9 L * ?");
        cron.setTimeZone(TimeZone.getTimeZone("Asia/Shanghai"));
        for (String[] dates : List.of(new String[]{"2026-02-01T00:00:00Z","2026-02-28T01:00:00Z"},
                new String[]{"2028-02-01T00:00:00Z","2028-02-29T01:00:00Z"},
                new String[]{"2026-09-01T00:00:00Z","2026-09-30T01:00:00Z"},
                new String[]{"2026-10-01T00:00:00Z","2026-10-31T01:00:00Z"}))
            assertEquals(Instant.parse(dates[1]),cron.getNextValidTimeAfter(Date.from(Instant.parse(dates[0]))).toInstant());
    }
}
