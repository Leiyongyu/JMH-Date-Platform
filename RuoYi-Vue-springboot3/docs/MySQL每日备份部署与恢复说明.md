# MySQL每日备份部署与恢复说明

## 功能

若依Quartz每天20:00调用`mysqlBackupTask.backup()`，分别备份`Date-Project`和`jmh_data_platform`。任务先在部署机本地完成SQL导出、ZIP压缩和解压校验，再复制到NAS临时目录；SHA-256复核通过后才发布为日期目录。

正常目录示例：

```text
\\UGREEN-9F8B\ywx123456_存储空间1\MySQL_Backup\2026-08-05\
  date-project_20260805_200000.sql.zip
  jmh_data_platform_20260805_200000.sql.zip
  SHA256SUMS.txt
  manifest.json
  RESTORE.txt
  backup.log
```

同一天手工补跑不会覆盖已有备份，而会使用`2026-08-05_HHmmss`目录。轮转只删除名称符合`YYYY-MM-DD`或`YYYY-MM-DD_HHmmss`且超出保留期的直接子目录，不会操作其他NAS文件。

## 部署前配置

必须使用实际运行Java服务的Windows账户登录，然后配置MySQL登录路径：

```powershell
& 'C:\Program Files\MySQL\MySQL Server 9.7\bin\mysql_config_editor.exe' set `
  --login-path=jmh_backup `
  --host=127.0.0.1 `
  --user=备份专用账号 `
  --password
```

密码会交互式输入，不得写入SQL、`application.yml`、Quartz调用参数或Git。

Java服务运行账户还必须拥有下列UNC目录的读取、创建、写入、改名和删除权限：

```text
\\UGREEN-9F8B\ywx123456_存储空间1\MySQL_Backup
```

不要用映射盘符。Windows服务如果使用`LocalSystem`，通常无法访问NAS，应改为具有NAS权限的专用账户。

可用环境变量覆盖默认配置：

```text
MYSQL_BACKUP_ENABLED=true
MYSQLDUMP_PATH=C:/Program Files/MySQL/MySQL Server 9.7/bin/mysqldump.exe
MYSQL_BACKUP_LOGIN_PATH=jmh_backup
MYSQL_BACKUP_DATABASE_DATE_PROJECT=Date-Project
MYSQL_BACKUP_DATABASE_ERP=jmh_data_platform
MYSQL_BACKUP_TEMP_DIR=D:/JMH_Backup_Temp
MYSQL_BACKUP_TARGET_DIR=//UGREEN-9F8B/ywx123456_存储空间1/MySQL_Backup
MYSQL_BACKUP_RETENTION_DAYS=30
MYSQL_BACKUP_TIMEOUT_MINUTES=120
MYSQL_BACKUP_MINIMUM_DUMP_BYTES=1024
```

## 注册任务

在`jmh_data_platform`执行：

```text
RuoYi-Vue-springboot3/sql/20260805_mysql_backup_job.sql
```

任务配置：

- Cron：`0 0 20 * * ?`
- 错过策略：立即执行一次
- 并发：禁止
- 状态：正常

部署并重启Java后，可在“系统监控 / 定时任务”中找到“MySQL双库每日全量备份”，先点击“执行一次”。确认两个ZIP、清单、日志全部生成后再依赖每日计划。

## 恢复

1. 对照`SHA256SUMS.txt`核对备份文件。
2. 使用Windows“解压缩全部”或`Expand-Archive`解压对应数据库ZIP。
3. 使用具备恢复权限的MySQL账号登录。
4. 在MySQL客户端用`SOURCE`执行SQL，路径使用正斜杠：

```text
mysql> SOURCE D:/restore/date-project_20260805_200000.sql;
mysql> SOURCE D:/restore/jmh_data_platform_20260805_200000.sql;
```

备份使用`--databases`，SQL包含数据库选择语句。正式恢复前应先恢复到临时MySQL实例进行演练，确认表数量和关键业务数据后再执行生产恢复。

## 安全和运维

- `backup.log`和若依定时任务日志会记录成功或失败原因，但不会记录数据库密码。
- NAS不可用、mysqldump失败、文件过小、ZIP损坏或复制后哈希不一致都会让Quartz任务标记失败。
- 发布成功前的NAS目录使用`.partial-*`名称；失败时只清理本次任务创建的临时目录。
- 本地失败诊断目录会保留在`MYSQL_BACKUP_TEMP_DIR`，排查后由管理员删除。
- 建议开启NAS快照、回收站和访问审计，并定期将备份复制到第二存储介质。
- 数据库可能包含第三方令牌，生产环境应结合NAS加密卷或加密备份存储。
