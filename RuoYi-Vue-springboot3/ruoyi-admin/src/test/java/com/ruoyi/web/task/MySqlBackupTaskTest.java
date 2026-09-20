package com.ruoyi.web.task;

import com.ruoyi.system.service.backup.MySqlBackupService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MySqlBackupTaskTest
{
    @AfterEach void clearContext() { OperationSyncContext.clear(); }

    private MySqlBackupService.BackupResult result(boolean warning)
    {
        return new MySqlBackupService.BackupResult("test-nas/today", 2, 100, 1, 2000,
                warning ? List.of(new MySqlBackupService.CleanupFailure("test-nas/old", "invalid directory")) : List.of());
    }

    @Test void cleanupWarningIsVisibleInSuccessfulQuartzContextAndSeparateAlert()
    {
        var service = mock(MySqlBackupService.class);
        var alerts = mock(SyncAlertService.class);
        when(service.backup()).thenReturn(result(true));
        new MySqlBackupTask(service, alerts).backup();
        assertEquals(OperationSyncResult.STATUS_SUCCESS, OperationSyncContext.get().getStatus());
        assertTrue(OperationSyncContext.get().toJobMessage(null).contains("备份成功，过期清理异常"));
        verify(alerts).sendAlert(eq("mysql-backup"), eq("retention"), anyString(),
                eq("mysqlBackupTask.backup()"), eq("WARNING"), contains("test-nas/old"), isNull());
        verify(alerts, never()).checkAndSendRecovery(anyString(), anyString(), anyString(), any());
    }

    @Test void notificationFailureCannotInvalidatePublishedBackup()
    {
        var service = mock(MySqlBackupService.class);
        var alerts = mock(SyncAlertService.class);
        when(service.backup()).thenReturn(result(true));
        doThrow(new IllegalStateException("notification unavailable")).when(alerts)
                .sendAlert(anyString(), anyString(), anyString(), anyString(), anyString(), anyString(), any());
        assertDoesNotThrow(() -> new MySqlBackupTask(service, alerts).backup());
        assertEquals(OperationSyncResult.STATUS_SUCCESS, OperationSyncContext.get().getStatus());
    }

    @Test void healthyCleanupChecksIndependentRecoveryChannel()
    {
        var service = mock(MySqlBackupService.class);
        var alerts = mock(SyncAlertService.class);
        when(service.backup()).thenReturn(result(false));
        new MySqlBackupTask(service, alerts).backup();
        verify(alerts).checkAndSendRecovery("mysql-backup", "retention", "MySQL备份过期清理", null);
        assertFalse(OperationSyncContext.get().toJobMessage(null).contains("清理异常"));
    }

    @Test void backupFailurePropagatesWithoutStaleSuccessContext()
    {
        var service = mock(MySqlBackupService.class);
        var alerts = mock(SyncAlertService.class);
        OperationSyncContext.set(OperationSyncResult.success("old", "old", "old", 2, 2, 1));
        when(service.backup()).thenThrow(new IllegalStateException("publication failed"));
        assertThrows(IllegalStateException.class, () -> new MySqlBackupTask(service, alerts).backup());
        assertNull(OperationSyncContext.get());
        verifyNoInteractions(alerts);
    }
}
