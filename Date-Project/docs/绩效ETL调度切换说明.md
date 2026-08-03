# 绩效 ETL 调度切换说明

## 正式链路

`Java Quartz → pythonPerformanceTask → Python内部任务接口 → ODS → DWD → AMZ DWS → 综合DWS`

旧 Java 本地 ETL 已移除，所有正式任务和补跑统一使用 Python 内部任务接口。

## 部署配置

Python 与 Java 必须配置相同的内部令牌：

```text
PYTHON_PERFORMANCE_INTERNAL_TOKEN=<高强度随机字符串>
```

Java 可选配置：

```text
PYTHON_PERFORMANCE_BASE_URL=http://127.0.0.1:8010
```

Python 未配置令牌时只允许本机访问内部接口；正式环境建议必须配置令牌。

## 部署顺序

1. 执行 Python 数据库迁移：
   `migrations/20260730_scheduler_etl_observability.sql`
2. 部署并重启 Python 服务。
3. 部署并重启 Java 服务。
4. 在若依任务管理中临时创建或手工调用：
   `pythonPerformanceTask.syncMonth('YYYY-MM')`
5. 核对：
   - `scheduler_task_run`
   - `performance_refresh_run`
   - `ods_lingxing_amz_order_profit_raw`
   - `dwd_amz_monthly_order_profit`
   - `dws_amz_performance_ranking`
   - `dws_combined_performance_ranking`
   - Java `data_sync_log`
   - Java `sys_job_log`
6. 同一月份再次补跑，确认 DWD 和 DWS 结果一致且无重复。
7. 执行 Java 切换脚本：
   `RuoYi-Vue-springboot3/sql/20260730_switch_job_240_to_python_performance.sql`
8. 重启 Java，或在任务管理页面修改并保存 `job_id=240`，刷新 Quartz 运行时配置。

## 正式任务配置

```text
job_id=240
invoke_target=pythonPerformanceTask.syncPreviousMonth()
cron_expression=0 0 22 4 * ?
misfire_policy=2
concurrent=1
status=0
```

## 故障处理

出现异常时先暂停 `job_id=240`，修复 Python 服务或数据后通过
`pythonPerformanceTask.syncMonth('YYYY-MM')` 补跑，再恢复正式任务。
旧 Java 本地 ETL 已删除，不再作为回滚目标。
