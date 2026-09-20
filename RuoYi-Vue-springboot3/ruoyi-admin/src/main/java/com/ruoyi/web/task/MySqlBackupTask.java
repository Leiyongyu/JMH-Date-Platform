package com.ruoyi.web.task;

import com.ruoyi.system.service.backup.MySqlBackupService;
import com.ruoyi.system.service.operation.sync.OperationSyncContext;
import com.ruoyi.system.service.operation.sync.OperationSyncResult;
import com.ruoyi.system.service.operation.sync.SyncAlertService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** 若依Quartz调用的MySQL每日全量备份任务。 */
@Component("mysqlBackupTask")
public class MySqlBackupTask
{
    private static final Logger log = LoggerFactory.getLogger(MySqlBackupTask.class);

    private final MySqlBackupService backupService;
    private final SyncAlertService alerts;

    public MySqlBackupTask(MySqlBackupService backupService, SyncAlertService alerts)
    {
        this.backupService = backupService;
        this.alerts = alerts;
    }

    public void backup()
    {
        OperationSyncContext.clear();
        MySqlBackupService.BackupResult result = backupService.backup();
        OperationSyncResult context = OperationSyncResult.success(
                "mysql_backup", "MySQL双库每日全量备份", "mysqlBackupTask.backup()",
                result.databaseCount(), result.databaseCount(), result.durationMillis());
        context.setBusinessSummary(result.summary());
        // Quartz reads and clears this context after invocation. Retention warnings are not FAILED.
        OperationSyncContext.set(context);
        if (result.hasCleanupWarnings())
            log.warn("ERP MySQL定时备份：{}", result.summary());
        else
            log.info("ERP MySQL定时备份：{}", result.summary());
        try
        {
            if (result.hasCleanupWarnings())
                alerts.sendAlert("mysql-backup", "retention", "MySQL备份过期清理",
                        "mysqlBackupTask.backup()", "WARNING", result.cleanupWarning(), null);
            else
                alerts.checkAndSendRecovery("mysql-backup", "retention", "MySQL备份过期清理", null);
        }
        catch (Exception e)
        {
            // Notification failures must not reclassify a successfully published backup.
            log.error("MySQL备份清理告警/恢复通知发送失败，本次备份结果不变", e);
        }
    }
}
