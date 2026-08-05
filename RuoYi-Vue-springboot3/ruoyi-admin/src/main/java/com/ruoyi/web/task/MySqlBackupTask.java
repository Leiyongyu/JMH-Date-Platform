package com.ruoyi.web.task;

import com.ruoyi.system.service.backup.MySqlBackupService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** 若依Quartz调用的MySQL每日全量备份任务。 */
@Component("mysqlBackupTask")
public class MySqlBackupTask
{
    private static final Logger log = LoggerFactory.getLogger(MySqlBackupTask.class);

    private final MySqlBackupService backupService;

    public MySqlBackupTask(MySqlBackupService backupService)
    {
        this.backupService = backupService;
    }

    public void backup()
    {
        MySqlBackupService.BackupResult result = backupService.backup();
        log.info("ERP MySQL定时备份成功：{}", result.summary());
    }
}
