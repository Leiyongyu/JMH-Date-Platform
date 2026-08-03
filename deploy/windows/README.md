# Windows 服务器部署

该 Python 仓库独立发布到 `git@github.com:Leiyongyu/Data-Project.git`。
Java/Vue 仓库发布到 `git@github.com:Leiyongyu/JMH-Date-Platform.git`。

## 1. 部署 Python API

服务器需安装 Git、Python 3.11+、MySQL 8，并让 Python 数据库账号同时拥有：

- 新建的 `Date-Project` 库（ODS/DWD/DWS、任务日志）读写权限；
- Java 库 `jmh_data_platform.shop_list` 的只读权限。

```powershell
git clone git@github.com:Leiyongyu/Data-Project.git D:\JMH\Data-Project
Set-Location D:\JMH\Data-Project
Copy-Item .env.example .env
notepad .env
powershell -ExecutionPolicy Bypass -File .\deploy\windows\install-service.ps1 `
  -InstallDir D:\JMH\Data-Project -Port 8010
```

`.env` 中必须设置 MySQL、领星凭据以及
`PYTHON_PERFORMANCE_INTERNAL_TOKEN`。首次安装会直接执行完整
`backend/schema.sql`，因此全新的 `Date-Project` 库无需另执行增量 SQL。
应用日志写入 `logs/date-project-api.log`，单文件 20 MB，保留 10 个轮转文件。

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/v1/health
Invoke-RestMethod http://127.0.0.1:8010/api/v1/finance/performance-months
Invoke-RestMethod http://127.0.0.1:8010/api/v1/finance/slow-moving-clearance/months
```

## 2. 部署 Java 和 Vue

Java 进程需要以下环境变量，token 必须与 Python `.env` 相同：

```powershell
[Environment]::SetEnvironmentVariable(
  "PERFORMANCE_PYTHON_BASE_URL",
  "http://127.0.0.1:8010/api/v1/finance",
  "Machine"
)
[Environment]::SetEnvironmentVariable(
  "PYTHON_PERFORMANCE_BASE_URL",
  "http://127.0.0.1:8010",
  "Machine"
)
[Environment]::SetEnvironmentVariable(
  "PYTHON_PERFORMANCE_INTERNAL_TOKEN",
  "替换为与Python一致的长随机值",
  "Machine"
)
```

在 Java 数据库执行
`RuoYi-Vue-springboot3/sql/20260730_deploy_python_finance.sql`，然后重新构建、
发布 Vue `dist` 和 `ruoyi-admin.jar`，最后重启 Java。SQL 会将：

- 绩效任务切换为 `pythonPerformanceTask.syncPreviousMonth()`；
- 滞销清货任务切换为 `pythonFbaInventoryTask.syncCurrentMonth()`；
- 保持每月 1 日 22:30 执行滞销清货 ETL；
- 补齐滞销清货菜单及 `leiyongyu` 权限。

## 3. 生产验证

先在若依任务管理中分别执行一次两个 Python 桥接任务，随后检查：

- `data_sync_log` 是否记录请求号、成功/失败、数量和耗时；
- Python `etl_scheduler_run_log` 是否为 `completed`；
- 绩效排名页面月份、AMZ/eBay/综合排名是否正常；
- 滞销清货页面是否仅展示 EU、US1、US2、US3，数量与成本汇总是否正常。
