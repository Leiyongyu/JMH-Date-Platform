package com.ruoyi.system.service.backup;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** ERP MySQL逻辑备份配置。 */
@Component
@ConfigurationProperties(prefix = "jmh.mysql-backup")
public class MySqlBackupProperties
{
    private boolean enabled = true;
    private String mysqldumpPath =
            "C:/Program Files/MySQL/MySQL Server 9.7/bin/mysqldump.exe";
    private String loginPath = "jmh_backup";
    private List<String> databases = new ArrayList<>(List.of(
            "Date-Project", "jmh_data_platform"));
    private String localTempDir = "D:/JMH_Backup_Temp";
    private String targetDir =
            "//UGREEN-9F8B/ywx123456_存储空间1/MySQL_Backup";
    private int retentionDays = 30;
    private int timeoutMinutes = 120;
    private long minimumDumpBytes = 1024L;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getMysqldumpPath() { return mysqldumpPath; }
    public void setMysqldumpPath(String mysqldumpPath) { this.mysqldumpPath = mysqldumpPath; }
    public String getLoginPath() { return loginPath; }
    public void setLoginPath(String loginPath) { this.loginPath = loginPath; }
    public List<String> getDatabases() { return databases; }
    public void setDatabases(List<String> databases) { this.databases = databases; }
    public String getLocalTempDir() { return localTempDir; }
    public void setLocalTempDir(String localTempDir) { this.localTempDir = localTempDir; }
    public String getTargetDir() { return targetDir; }
    public void setTargetDir(String targetDir) { this.targetDir = targetDir; }
    public int getRetentionDays() { return retentionDays; }
    public void setRetentionDays(int retentionDays) { this.retentionDays = retentionDays; }
    public int getTimeoutMinutes() { return timeoutMinutes; }
    public void setTimeoutMinutes(int timeoutMinutes) { this.timeoutMinutes = timeoutMinutes; }
    public long getMinimumDumpBytes() { return minimumDumpBytes; }
    public void setMinimumDumpBytes(long minimumDumpBytes) { this.minimumDumpBytes = minimumDumpBytes; }
}
