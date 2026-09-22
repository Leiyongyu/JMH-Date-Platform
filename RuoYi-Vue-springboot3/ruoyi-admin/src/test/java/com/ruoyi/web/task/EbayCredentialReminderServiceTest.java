package com.ruoyi.web.task;

import com.ruoyi.system.service.finance.PythonPerformanceSchedulerClient;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class EbayCredentialReminderServiceTest
{
    private EbayCredentialReminderService task(PythonPerformanceSchedulerClient client, SyncAlertService alerts)
    {
        var task = new EbayCredentialReminderService(client, alerts);
        ReflectionTestUtils.setField(task, "enabled", true);
        return task;
    }

    @Test void validTokensAndMissingTokensDoNotSendReminder()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var alerts = mock(SyncAlertService.class);
        when(client.ebayCredentialExpiry(anyString())).thenReturn(Map.of("data", Map.of(
            "checked_on", "2026-09-19", "accounts", List.of(Map.of("status", "VALID")),
            "missing_credentials", List.of(Map.of("shop_name", "missing")))));
        task(client, alerts).checkDaily();
        verifyNoInteractions(alerts);
    }

    @Test void dueReminderGroupsShopsAndUsesExistingWecom()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var alerts = mock(SyncAlertService.class);
        when(client.ebayCredentialExpiry(anyString())).thenReturn(Map.of("data", Map.of(
            "checked_on", "2028-02-18", "accounts", List.of(
                Map.of("status", "EXPIRING", "expires_on", "2028-03-18", "shop_name", "shop-a"),
                Map.of("status", "EXPIRING", "expires_on", "2028-03-18", "shop_name", "shop-b")))));
        when(alerts.sendCredentialReminder(anyString(),anyString())).thenReturn(true);
        task(client, alerts).checkDaily();
        verify(alerts).sendCredentialReminder(eq("EXPIRING:2028-03-18:2028-02-18"),
            argThat(content -> content.contains("店铺数：2") && content.contains("shop-a") && content.contains("2028-03-18")));
        verifyNoMoreInteractions(alerts);
    }

    @Test void failedCheckIsVisibleWithoutRawExceptionText()
    {
        var client = mock(PythonPerformanceSchedulerClient.class);
        var alerts = mock(SyncAlertService.class);
        when(client.ebayCredentialExpiry(anyString())).thenThrow(new RuntimeException("sensitive-token"));
        task(client, alerts).checkDaily();
        verify(alerts).notifyBackgroundFailure(eq("ebay_credential_expiry"),anyString(),
            argThat(message -> !message.contains("sensitive-token")));
    }
}
