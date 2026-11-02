# 平台优化部署说明（refactor/platform-optimization）

本分支对应架构审查报告中除「第 1 周」（密钥外置、Druid 控制台、代理令牌改 cookie）以外的优化项。
按下面顺序部署；每一步都可以单独回滚。

## 0. 先决条件

- 三个子项目都要重建：`RuoYi-Vue3-master` 执行 `npm run build:prod`，`RuoYi-Vue-springboot3` 执行
  `mvn -DskipTests clean package`，Python 改了源码重启即可。前端发布后提醒大家 Ctrl+F5。
- Java 新增依赖 actuator / micrometer-prometheus，部署机打包时需要能访问 Maven 仓库。

## 1. 数据库迁移版本管理（一次性）

服务启动时**不再自动执行建表/补列**（`DATABASE_AUTO_MIGRATE=false`）。结构变更统一用命令执行并留痕：

```powershell
Set-Location D:\JMH_Project\Project\JMH-Date-Platform\Date-Project
# 查看两个库的迁移状态（只读）
.\.venv\Scripts\python.exe -m backend.cli db-status --target all
```

存量环境第一次上线时，把「已经执行过的」历史脚本登记为基线（不执行 SQL）：

```powershell
# 截至 20261028 的脚本已按部署回执执行；之后的文件留作待执行迁移
# Python 库：会先重放一次原来每次启动都会跑的幂等建表脚本，再登记
.\.venv\Scripts\python.exe -m backend.cli db-baseline --target date --through 20261028_zzz
# ERP 库：只登记，不执行任何 SQL
.\.venv\Scripts\python.exe -m backend.cli db-baseline --target erp --through 20261028_zzz
```

`--through` 之后的文件就是待执行迁移。先预览、再执行：

```powershell
.\.venv\Scripts\python.exe -m backend.cli db-migrate --target all --dry-run
.\.venv\Scripts\python.exe -m backend.cli db-migrate --target all
```

本分支新增的待执行迁移：

| 库 | 文件 | 内容 |
|---|---|---|
| date | `20261102_inventory_purchase_order_api.sql` | Codex 新增的采购在途表（Codex 提交说明里的「新增 SQL」） |
| date | `20261102_scheduler_task_quality_check.sql` | 数据质量检查结果表 |
| erp | `20261029_pending_purchase_order_status.sql`、`20261030_sales_dashboard_finance_menu.sql`、`20261102_inventory_purchase_order_job.sql` | Codex 分支上尚未执行的菜单/任务脚本（执行前请确认部署回执） |

基线是「按部署回执，截至该日期的脚本都已执行」的假设；如果某个旧脚本其实没执行过，
`db-status` 不会发现，需要按回执人工核对。

约定：

- 新的结构变更 = 新增 `YYYYMMDD_描述.sql`，**不要修改已执行的文件**（`db-migrate` 会因校验和变化拒绝执行）。
- `*_rollback.sql`、`*_verify.sql`、`*_validate.sql` 只供人工使用，不会被自动执行。
- 某个迁移执行失败会记为 `failed` 并停止；人工确认处理后重新执行 `db-migrate` 即可。

## 2. 拆分数据库账号

1. DBA 打开 `create_app_accounts.sql`，把三个 `<...>` 占位符替换成新生成的密码后执行。
2. Python `.env`：`MYSQL_USER=py_app`、`MYSQL_PASSWORD=...`，`MYSQL_MIGRATOR_USER=migrator`、
   `MYSQL_MIGRATOR_PASSWORD=...`，重启 Python。
3. Java：`DB_USERNAME=erp_app`。**Java 密码目前硬编码在 `application-druid.yml`，属于第 1 周的密钥外置项**，
   要等那一项改成 `${DB_PASSWORD}` 后 Java 才能切到 `erp_app`。

回滚：把账号改回原值并重启。

## 3. eBay 补货规则表迁回 Date-Project 库（可选，需停机窗口）

按 `move_ebay_replenishment_rules.sql` 文件头的步骤执行，完成后在 `.env` 设置
`EBAY_REPLENISHMENT_RULE_DATABASE=Date-Project` 并重启 Python。删掉这一行即回滚。

## 4. 数据质量门禁

每个定时任务成功后，自动与最近 5 次成功运行比较跳过占比、空抽取、抽取量骤降/暴增，
结果写入 `scheduler_task_quality_check`。

- 默认 `DATA_QUALITY_MODE=warn`：只记录和写告警日志，不影响任务。
- 观察一两周、确认没有误报后改为 `block`：阻断级问题会让任务失败，并沿用现有的 Quartz 失败告警邮件。
- 个别任务需要放宽阈值时，修改 `backend/services/data_quality.py` 里的 `TASK_THRESHOLDS`。

```sql
SELECT task_code, status, issues, checked_at
FROM scheduler_task_quality_check WHERE status <> 'passed' ORDER BY checked_at DESC LIMIT 50;
```

## 5. Java 运行参数（均有默认值，可按需用环境变量调整）

| 变量 | 默认 | 说明 |
|---|---|---|
| `SERVER_TOMCAT_MAX_THREADS` | 200（原 800） | 与连接池保持约 4:1 |
| `DB_POOL_MAX_ACTIVE` | 50（原 20） | Druid 最大连接数 |
| `DB_POOL_MAX_WAIT_MS` | 10000（原 60000） | 连接池耗尽时快速失败 |
| `LOG_LEVEL_RUOYI` | info（原 debug） | |
| `JMH_PYTHON_BASE_URL` / `PYTHON_INTERNAL_API_TOKEN` | — | 七个 Python 模块统一读这两项 |
| `JMH_PYTHON_TIMEOUT_{FAST,REPORT,LONG,ETL}_MS` | 120s / 300s / 900s / 3h | 读超时档位 |
| `MANAGEMENT_PORT` | 8081，仅监听 127.0.0.1 | 健康检查与指标 |

健康检查与指标（只能在部署机本机访问）：

```powershell
curl http://127.0.0.1:8081/actuator/health
curl http://127.0.0.1:8081/actuator/prometheus
```

## 6. 长任务异步化

Java 调 Python 定时任务改为「提交 → 拿 run_id → 每 10 秒轮询」，不再用一条 HTTP 连接等待最长 3 小时。
Python 未升级时，Java 会自动退回原同步接口，所以两端部署先后顺序不限。
运行状态保存在 Python 进程内存中，要求 uvicorn 以单进程运行（现有启动脚本均如此）。

## 7. CI 与分支保护

`.github/workflows/ci.yml` 会在 push 到 main 和每个 PR 上运行 Python / Java / 两个前端的测试与构建。
建议在 GitHub 仓库 Settings → Branches 给 `main` 打开「Require status checks to pass」，
勾选 CI 的四个 job。

## 8. 下线「数据中心 > 售后数据」页面

页面、Java 接口与 AMZ-SOP 售后定时任务代码已删除。部署新版代码后执行（均已纳入迁移，`db-migrate --dry-run` 可见）：

| 库 | 文件 | 内容 |
|---|---|---|
| erp | `20261103_remove_after_sales_page.sql` | 删除售后数据菜单与 4 个按钮、角色授权、「AMZ-SOP售后链路」Quartz 任务 |
| date | `20261103_drop_after_sales_tables.sql` | **删除 16 张售后专用表（不可恢复）**，删除 Python 调度任务定义 |

- 执行前确认当天 MySQL 备份已成功。
- 保留 `dim_amz_sop_after_sales_category`：eBay SKU 分析页面仍在使用。
- 执行后重启 Java，用户重新登录即可看到菜单消失。
