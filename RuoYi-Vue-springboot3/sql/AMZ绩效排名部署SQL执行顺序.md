# AMZ 绩效排名部署 SQL 执行顺序

适用数据库：`jmh_data_platform`

全新环境和已部署过旧版绩效排名的环境，都按照下面的顺序执行。两份 SQL 均按可重复执行设计，不需要删除旧表或清空历史数据。

## 第 0 步：确认当前数据库

```sql
USE `jmh_data_platform`;
SELECT DATABASE();
```

确认查询结果为 `jmh_data_platform` 后再继续。

## 第 1 步：执行完整基础脚本

执行文件：

```text
20260727_amz_monthly_order_profit_performance.sql
```

该脚本按顺序完成：

1. 创建 `amz_monthly_order_profit` 月度完整订单利润表。
2. 创建 `amz_performance_owner_rule` 月度负责人匹配规则表。
3. 创建 `amz_performance_ranking` 负责人绩效排名汇总表。
4. 创建或更新“Amazon月度完整订单利润同步”定时任务。
5. 创建财务中心下的“绩效排名”菜单。
6. 创建查询、编辑权限标识。
7. 给 `leiyongyu` 所属角色补齐菜单、查询和编辑权限。

必须先执行该文件。它会确保后续升级脚本引用的表、菜单和定时任务已经存在。

## 第 2 步：执行负责人规则及净销售额升级脚本

执行文件：

```text
20260728_amz_performance_owner_rule.sql
```

该脚本按顺序完成：

1. 兼容已部署过旧版绩效排名的数据库。
2. 确保 `amz_performance_owner_rule` 表存在。
3. 将历史负责人值“待定”“待到”统一改为“未分配”。
4. 确保 `amz_performance_ranking.net_sales_amount` 字段存在。
5. 净销售额字段定义为：`销售额 - 退款金额`。
6. 再次补齐 `leiyongyu` 的绩效排名页面权限。

即使第 1 步已经创建了最新表结构，也要继续执行第 2 步。这样可以同时兼容部署机原来已经存在的旧表。

## 第 3 步：执行部署校验 SQL

```sql
-- 1. 三张业务表必须全部存在
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'amz_monthly_order_profit',
    'amz_performance_owner_rule',
    'amz_performance_ranking'
  )
ORDER BY TABLE_NAME;

-- 2. 排名表必须包含净销售额字段
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'amz_performance_ranking'
  AND COLUMN_NAME IN (
    'stat_month',
    'principal_name',
    'gross_profit',
    'amount',
    'refund_amount',
    'net_sales_amount',
    'create_time',
    'update_time'
  )
ORDER BY ORDINAL_POSITION;

-- 3. 月度利润定时任务应只有一条有效链路
SELECT job_id, job_name, job_group, invoke_target, cron_expression, status
FROM sys_job
WHERE invoke_target IN (
  'operationSyncTask.syncAmzMonthlyOrderProfit',
  'operationSyncTask.syncAmzMonthlyOrderProfit()'
)
ORDER BY job_id;

-- 4. 绩效排名菜单和按钮权限
SELECT menu_id, parent_id, menu_name, path, component, menu_type, perms, visible, status
FROM sys_menu
WHERE path = 'performance-ranking'
   OR perms IN (
     'finance:performanceRanking:list',
     'finance:performanceRanking:edit'
   )
ORDER BY menu_id;

-- 5. leiyongyu 的角色权限
SELECT DISTINCT
  u.user_name,
  r.role_name,
  m.menu_name,
  m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
JOIN sys_role_menu rm ON rm.role_id = r.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND (
    m.path = 'performance-ranking'
    OR m.perms IN (
      'finance:performanceRanking:list',
      'finance:performanceRanking:edit'
    )
  )
ORDER BY r.role_name, m.menu_id;
```

预期结果：

- 第一个查询返回三张表。
- 第二个查询包含 `net_sales_amount`。
- 定时任务调用目标为 `operationSyncTask.syncAmzMonthlyOrderProfit()`，Cron 为 `0 0 22 4 * ?`。
- 菜单包含“绩效排名”“绩效排名查询”“绩效排名编辑”。
- `leiyongyu` 至少具有页面菜单、查询权限和编辑权限。

## SQL 执行完成后的操作

1. 拉取最新代码并重启 Java 后端。
2. 前端重新构建部署；本地开发环境可直接使用 Vue 热更新。
3. 让 `leiyongyu` 退出后重新登录，以刷新菜单和权限缓存。
4. 进入“财务中心 → 绩效排名”，导入负责人配置 Excel。
5. 点击“重新匹配并汇总”，生成毛利润和净销售额排名数据。
