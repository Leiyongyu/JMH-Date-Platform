# OperationAssistant 接入 ERP 部署说明

## 1. 最终架构

ERP 继续负责账号、角色、菜单和权限。用户点击“运营中心 / 运营助手”后，若依侧边栏直接在新窗口打开同域的 OperationAssistant 门户，不再把门户嵌入 ERP 页面；Nginx 在门户及四个业务服务前执行 `auth_request`，调用 Java 接口 `/operations/assistant/auth-check` 校验若依登录状态和 `operations:assistant:view` 权限。

OperationAssistant 不再显示独立登录页，也不再依赖原来的 `users.db` 和 8010 鉴权服务。原鉴权源码暂时保留用于回滚，但不会进入当前页面流程。

| 路径 | 服务 | 本机端口 |
| --- | --- | ---: |
| `/operation-assistant/hub/` | 运营助手门户静态文件 | Nginx 静态目录 |
| `/listing/` | 领星刊登 | 8001 |
| `/replenishment/` | 补货表自动填充 | 8000 |
| `/sop/` | SOP 图片生成 | 8002 |
| `/sku/` | 批次库存自动填充 | 3000 |

## 2. 数据库备份核对结果

已核对 `OperationAssistant_DB_20260803_162834` 中的实际文件及代码读写关系：

| 文件 | 业务表 | 备份数据量 | 用途和处理方式 |
| --- | --- | ---: | --- |
| `listing_store.db` | `drafts` / `tasks` / `score_history` | 4 / 5 / 10 | 对应程序运行库 `apps/product-listing/data/store.db`（或 `LISTING_DB_PATH`）；刊登草稿和异步任务仍由 `record_store.py` 使用。`score_history` 当前代码未读取，作为历史数据保留 |
| `listing_local_store.db` | 同上 | 0 / 0 / 10 | 本地副本，不能覆盖服务器在线库 |
| `sop_sop.db` | `drafts` / `ai_profile_cache` | 15 / 6 | 对应程序运行库 `apps/sop/output/sop.db`（或 `DB_PATH`）；分别用于 SOP 草稿和 AI 分析缓存 |
| `sop_local_sop.db` | 同上 | 0 / 0 | 空的本地副本，不能覆盖服务器在线库 |
| `replenishment_redis.rdb` | Redis 快照 | 无业务键 | 当前备份中没有可恢复的补货任务；运行时仍可使用 Redis/内存任务队列 |

这些数据不迁入 `jmh_data_platform`：它们是各工具的运行态草稿、任务和缓存，不是 ERP 主数据。ERP 数据库只需执行菜单权限 SQL，不新增业务表。

备份目录中的文件名带应用前缀，恢复时不能原名直接放入程序目录：`listing_store.db` 应恢复为刊登服务的 `store.db`，`sop_sop.db` 应恢复为 SOP 服务的 `sop.db`。部署或更新程序时，禁止覆盖服务器现有主库及对应 WAL/SHM 文件。SQLite 在线备份应使用 SQLite backup API，或先停止对应服务并完成 checkpoint 后整体复制主库和 WAL/SHM。

## 3. ERP 数据库

在 `jmh_data_platform` 执行：

`RuoYi-Vue-springboot3/sql/20260803_operation_assistant_erp_integration.sql`

脚本只操作 `sys_menu` 和 `sys_role_menu`，可重复执行，会为管理员及账号 `leiyongyu` 当前拥有的全部角色授权，不会修改其他业务表。执行后让用户重新登录，刷新动态路由。

Windows 部署机不要使用 PowerShell 的 `Get-Content | mysql` 管道执行包含中文的 SQL，Windows PowerShell 5.1 可能把中文转换成问号。先进入 SQL 所在目录，再进入 MySQL 客户端使用相对文件名执行 `SOURCE`：

```powershell
Set-Location 'D:\JMH\项目\JMH-Date-Platform\RuoYi-Vue-springboot3\sql'
mysql -h localhost -u root -p --default-character-set=utf8mb4 jmh_data_platform
```

```text
mysql> SOURCE 20260803_operation_assistant_erp_integration.sql;
```

## 4. 构建 OperationAssistant 门户

在 Windows PowerShell 中执行：

```powershell
Set-Location 'D:\JMH\项目\OperationAssistant'
$env:VITE_PORTAL_BASE='/operation-assistant/hub/'
$env:VITE_ERP_INTEGRATION='true'
npm.cmd install
npm.cmd run build
```

把 `dist` 目录内的文件复制到 Nginx 静态根目录：

```text
D:\JMH\nginx\html\operation-assistant\hub\
```

ERP 开发环境默认访问 `http://127.0.0.1:5175/hub/`；生产和 staging 环境访问同域 `/operation-assistant/hub/`。

## 5. Nginx 与 Java

1. 部署最新的若依 Java 后端，确保接口 `/operations/assistant/auth-check` 可用。
2. 将 `docs/OperationAssistant-ERP-Nginx.conf.example` 中两个 `map` 放入 Nginx 的 `http` 块，并将各 `location` 放入 ERP 所在的 `server` 块。
3. 若 Java 后端端口或静态目录不同，修改示例中的 `127.0.0.1:8080` 和 `D:/JMH/nginx/html`。
4. 执行 `nginx -t` 后再重载 Nginx。

必须让门户和四个工具通过 ERP 的同一个域名访问，浏览器才会自动携带 `Admin-Token` Cookie。不要把 ERP iframe 配置为另一台服务器的裸 IP。

## 6. 服务和验证顺序

1. 启动刊登服务 8001、补货服务 8000、SOP 服务 8002、SKU 服务 3000。
2. 启动若依 Java 后端和 ERP 前端。
3. 用 `leiyongyu` 重新登录，确认“运营中心 / 运营助手”菜单出现。
4. 依次打开四个工具，验证页面、上传、下载、长任务和健康检查。
5. 退出 ERP 后直接访问任一 `/listing/`、`/replenishment/`、`/sop/`、`/sku/`，应返回 401，确认无法绕过 ERP 权限。
6. 全部通过后，可以停止旧的 8010 独立鉴权服务；不要删除其数据，保留一次回滚周期。
