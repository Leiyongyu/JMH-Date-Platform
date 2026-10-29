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

### 2026-09-20：区分备份失败与过期清理异常

- 导出、压缩、校验或 NAS 发布失败仍抛出异常，Quartz 标记失败，原有失败告警不变。
- 新备份发布成功后，过期目录逐个清理；某个目录清理失败时记录路径和完整异常，继续处理其他过期目录。目录枚举失败也作为清理警告报告。
- 仅清理失败时，Quartz 状态为成功，但执行信息明确显示“备份成功，过期清理异常”。Java 日志保留全部异常路径；企微通过独立的 `mysql-backup / retention` 通道发送 `WARNING`，不依赖成功通知开关。该通道使用现有告警总开关、Webhook 和去重配置。
- 后续清理恢复正常时，调用现有恢复通知机制（是否发消息受 `sync.alert.notify-recovery` 控制）。告警发送异常只记日志，不改变已发布备份的结果。
- 没有放宽保留期、直接子目录、目录命名及符号链接防护；不会尝试强制修复或强制删除 NAS 损坏对象。一次清理可能在部分文件删除后失败，不具备回滚能力；已清理目录数只计完整删除成功的目录。
- `backup.log` 和 `manifest.json` 仍是发布前生成的备份材料；发布后的清理结果以 Quartz 执行信息和 Java 日志为准。压缩包校验通过不等于数据库恢复演练通过。

部署本次修复只需重新构建、发布 `ruoyi-admin.jar` 并重启 Java；**无需 SQL、无需修改任务 236、无需改 UNC 配置，也不需要重跑旧日期备份**。代码不能修复 `2026-08-06/backup.log` 在 NAS 上的文件/目录类型不一致问题，仍需由 NAS 管理员单独排查。

回归测试使用临时合成文件及模拟异常，不调用 mysqldump、不连接 NAS、数据库或企微：

```powershell
mvn -pl ruoyi-admin -am '-Dtest=MySqlBackupServiceTest,MySqlBackupTaskTest' '-Dsurefire.failIfNoSpecifiedTests=false' test
```

- `backup.log`和若依定时任务日志会记录成功或失败原因，但不会记录数据库密码。
- NAS不可用、mysqldump失败、文件过小、ZIP损坏或复制后哈希不一致都会让Quartz任务标记失败。
- 发布成功前的NAS目录使用`.partial-*`名称；失败时只清理本次任务创建的临时目录。
- 本地失败诊断目录会保留在`MYSQL_BACKUP_TEMP_DIR`，排查后由管理员删除。
- 建议开启NAS快照、回收站和访问审计，并定期将备份复制到第二存储介质。
- 数据库可能包含第三方令牌，生产环境应结合NAS加密卷或加密备份存储。


### 2026-10-29：NAS把backup.log文件错误标记为目录

只读实机核验发现：12个过期日期目录里的 `backup.log`，GetFileAttributes/lstat均返回目录属性，但以文件句柄打开后fstat确认是普通文件；按目录枚举返回WinError 267“目录名称无效”。当天新备份日志也存在同样情况。共享根路径可访问，不能把该错误等同于路径拼写错误或权限不足。

清理前针对备份日期目录直属的 `backup.log` 增加兼容处理：仅在属性报目录、不是符号链接且实际文件句柄可读时，使用NIO DELETE_ON_CLOSE按文件句柄删除；关闭后确认路径消失，再继续原目录树清理。真实目录、符号链接及其他文件名不进入该分支。保持30天保留期、直接子目录及不跟随链接的边界。失败仍报告清理WARNING，不屏蔽异常、不强制改NAS属性。

本地17项备份相关测试通过，使用临时文件模拟错误属性，未调用真实mysqldump、NAS删除或恢复。实机删除需要用户授权；Java修复随代码发布后重新打包并重启生效，测试阶段未重启服务。

已只读确认的待清理日期为：2026-08-06、08-16、08-17、08-18、08-24、08-25、08-26、08-27、09-03、09-09、09-10、09-16（均为2026年），目录条目显示的文件总量约720MB。它们不包含2026-10-29的新备份。Windows返回的错误目录属性令日志大小显示0，实际日志内容很小，因此大小仅作为估算。


用户已明确授权仅清理上述12个过期目录。2026-10-29通过向日葵执行前逐一验证直接子目录、日期白名单、六个标准文件名、无符号链接/重解析点及实际文件句柄类型；使用非递归文件删除及目录删除，避开SMB错误目录属性。执行回执显示12个目录全部删除、0失败，文件逻辑大小合计720036233字节。执行前后对2026-10-29备份所有文件计算SHA-256并核对，结果一致；未授权根目录条目清单一致；未执行数据库操作。部署机回执：项目 `.codex-temp/nas_approved_cleanup_receipt_20261029.json`。此次实机清理使用一次性受限脚本，Java兼容修复需在更新代码、重新打包并重启后生效，不将手工清理成功表述为新版Java已上线验证。
