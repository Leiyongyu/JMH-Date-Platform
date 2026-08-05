# JMH Date-Platform 多人协同开发规范

> 适用仓库：`git@github.com:Leiyongyu/JMH-Date-Platform.git`
> 后端：Python FastAPI（`Date-Project/`）；ERP 联动：`RuoYi-Vue-springboot3/`（Java）
> 本文件重点是 Python 侧协作规范，Java 侧沿用若依团队的约定。

---

## 1. 分支与开发流程

- `main` 为受保护分支，**禁止直接 push**，一律通过 PR 合入。
- 分支命名（`git checkout -b`）：

| 类型 | 命名 |
|---|---|
| 新功能 | `feature/<模块>-<简述>`，如 `feature/ebay-price-cache` |
| 缺陷修复 | `fix/<模块>-<简述>`，如 `fix/performance-null-sku` |
| 重构 | `refactor/<模块>-<简述>`，如 `refactor/client-consolidate` |
| 性能 | `perf/<模块>-<简述>`，如 `perf/ebay-search-concurrency` |
| 文档 | `docs/<简述>` |

- 提交前先 `git pull origin main` 拉最新，解决冲突后再提 PR。
- PR 描述写清楚：改了什么、为什么改、影响哪些接口/表、是否需重建数据。

---

## 2. 模块划分与分工

**按业务模块切「垂直切片」，每人负责一条竖线，文件互不重叠：**

| 模块 | API 入口 | 主要文件 |
|---|---|---|
| 绩效排名 | `api/v1/finance.py` | `schemas/performance_requests.py`、`services/performance_service.py`、`repositories/performance_repository.py`、`parsers/performance_*.py` |
| eBay 价格 | `api/v1/ebay_price.py` | `schemas/ebay_price_requests.py`、`services/ebay_price_service.py`、`repositories/ebay_price_repository.py`、`integrations/ebay/` |
| 领星同步 | `api/v1/lingxing.py` | `services/lingxing_service.py`、`integrations/lingxing/` |
| 外汇退税 | `api/customs.py` `api/upload.py` `api/export.py` | `backend/customs_*.py`、`importer.py`、`exporter.py`、`parsers/customs_declaration_parser.py` |
| 库存 | `api/v1/inventory.py` | `services/inventory_service.py`、`repositories/` |
| 定时任务 | `api/v1/internal_scheduler.py` | `services/scheduler_service.py`、`services/amazon_profit_sync_service.py`、`services/clearance_service.py` |

**共享文件（改动前先通知大家）：**
`main.py`、`api/router.py`、`config.py`、`database.py`、`schema.sql`、`infrastructure/`、`schemas/responses.py`、`api/deps.py`

> 新增模块 = 在 `api/` 下建新文件 + 在 `api/router.py` 加一行 `include_router`。

---

## 3. 分层约束（不允许破坏）

```
API 层       只做参数校验、状态码、统一响应，不写业务 SQL
Service 层   业务流程编排（导入、查询、ETL、调用外部 API）
Repository 层只做数据库读写，不写复杂业务判断
Integration 层只负责外部接口（领星、eBay），不写数据库
```

三条红线：
- API 不能直接访问数据库；
- Repository 不能调用外部 API；
- Integration 不能写数据库。

---

## 4. 命名与风格

- **Python 文件**：`snake_case`，业务模块后缀固定 `_service` / `_repository` / `_requests` / `_parser`。
- **DB 表**：

| 前缀 | 用途 | 示例 |
|---|---|---|
| `dim_` | 维度/配置 | `dim_ebay_sku_oe_mapping` |
| `ods_` | 原始数据 | `ods_lingxing_amz_order_profit_raw` |
| `dwd_` | 清洗明细 | `dwd_amz_monthly_order_profit` |
| `dws_` | 汇总结果 | `dws_combined_performance_ranking` |
| `job_` / `scheduler_` | 任务日志 | `scheduler_task_run` |
| `stg_` | 临时表 | 批处理导入暂存 |

- 常量用 `UPPER_SNAKE_CASE`，禁止硬编码密钥/路径。
- 新增配置键必须同步写入 `.env.example`（只放占位符，不放真实值）。

---

## 5. 配置与密钥管理

- `.env` 已加入 `.gitignore`，**禁止 `git add .env`**；若误提交过，用 `git rm --cached .env` 并从仓库历史清除后再轮换密钥。
- 每个开发者本地自己建 `.env`，从 `.env.example` 复制。
- 密钥清单（不得写进代码/注释/日志）：
  `MYSQL_PASSWORD`、`LINGXING_APP_ID`、`LINGXING_APP_SECRET`、`EBAY_CLIENT_ID`、`EBAY_CLIENT_SECRET`、`PYTHON_INTERNAL_API_TOKEN`。
- 内部 token 统一用 `PYTHON_INTERNAL_API_TOKEN`（Java 侧同名环境变量），**不要新增第二个内部 token 变量**。

---

## 6. 数据库变更

- `database.py` 里的 `_ensure_*` 和 `schema.sql` 是**最大冲突热点**。涉及表结构变更前，先同步别人，避免多人同时改同一张表。
- 表结构变更建议遵守：新增列用 `ADD COLUMN` 幂等写法；索引先查 `SHOW INDEX` 再建。
- 大的批量改动（如整表重建）放到 PR 说明里，提示部署时数据量。

---

## 7. 接口设计规范（RESTful + 统一响应）

### RESTful 资源设计

- URL 用复数名词 + 层级路径，不用动词/驼峰：
  - 正确：`/api/v1/finance/performance-rankings`
  - 避免：`/api/v1/finance/getRankings`
- HTTP 方法语义：
  - `GET` 查询资源；`POST` 创建资源；`PATCH`/`PUT` 修改；`DELETE` 删除。
  - 触发型操作放**子资源**：`POST /tasks/{task_code}/runs`（创建一次运行），而不是 `POST /tasks/{task_code}/run`。
  - 状态切换用 `PATCH`：`PATCH /tasks/{task_code}` body `{"enabled": true}`，而不是 `/enable`、`/disable`。
- 现有动作式端点（`searches`/`exports`/`imports`/`refreshes`/`enable`/`disable`/`probe`）属于历史 RPC 风格，**对外契约已定，暂不破坏**；新增接口一律按 RESTful 编写。

### 统一响应（所有接口，含错误）

```
成功：{"code": 0,          "message": "success", "data": {...}, "request_id": "..."}
失败：{"code": <http状态码>, "message": "...",   "data": null,   "request_id": "..."}
```

- 错误统一由 `infrastructure/exception_handlers.py` 兜底：`HTTPException` → 对应状态码；参数校验 → 422；未捕获异常 → 500。
- API 层**不要**自己 `try/except` 后返回裸 dict；抛 `HTTPException(status_code, detail)` 或直接上抛，由全局 handler 统一转换。
- `message` 不得包含堆栈/内部路径，细节只写日志。
- 查询接口统一分页参数 `page` / `page_size`，返回 `total` / `pagination`。
- 写接口可用 `Idempotency-Key` 请求头做幂等。

---

## 8. 提交规范（Conventional Commits）

统一采用 Conventional Commits，`type` 用英文，描述用中文（和现有仓库风格一致）：

```
<type>(<scope>): <描述>
```

### type（必填）

| type | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修复缺陷 |
| `refactor` | 重构（不改功能） |
| `perf` | 性能优化 |
| `test` | 测试 |
| `docs` | 文档 |
| `chore` | 构建/配置/杂项 |
| `security` | 安全修复 |

### scope（可选，写模块名）

`finance` / `ebay-price` / `lingxing` / `performance` / `customs` / `inventory` / `scheduler` / `client` / `deploy`

### 描述规范

- 中文，简短（≤ 50 字），动词开头，说明「做了什么」而非「怎么做的」。
- 同一功能多个点，拆多条提交，**一次提交只做一个逻辑变更**。

### 好的示例

```
feat(ebay-price): 增加 SKU-OE 对照导入接口
fix(performance): 修复负责人规则为空时排名报错
perf(finance): eBay 多 OE 查询改为并发
refactor(client): 统一三个 Python HTTP 客户端
docs: 补充多人协同开发规范
```

### 坏的示例

```
update            （没有 type）
fix bug           （描述不清晰）
优化代码           （没有 type，范围不明）
feat: 加了好多东西，改了很多文件   （一次提交包含多个逻辑）
```

### 提交前检查

```bash
git status                 # 确认只包含本模块相关文件
git diff                   # 检查是否有 .env、密钥、临时文件、logs/
git diff --cached          # 检查暂存内容
git log --oneline -5       # 确认 commit 风格
```

- 禁止提交：`.env`、`*.log`、`.run/`、`tmp/`、`outputs/`、`__pycache__/`、本地 Excel/导出文件。
- 提交信息如有拼写错误或需要补充，用 `git commit --amend`（仅限未 push 的本地提交）。

---

## 9. 提交前必须验证

```powershell
# 后端
.venv\Scripts\python.exe -m pytest tests -q        # 跑全部测试
.venv\Scripts\python.exe -m compileall -q backend  # 语法检查
# 建议后续接入 ruff：
# .venv\Scripts\python.exe -m ruff check backend
```

- 改动接口时，用 `/docs`（Swagger）验证请求/响应格式未变。
- 改动影响 ERP 联调的（`finance` / `internal/scheduler` / `upload`），提示 Java 侧注意点（如 token、错误格式）。

---

## 10. 代码审查清单（PR 合并前）

- [ ] 分层约束是否遵守（API 没直接查库、Repository 没调外部接口）
- [ ] 密钥/路径没有硬编码
- [ ] 异步接口是否避免阻塞事件循环（`async def` 里不跑同步重活，用 `run_in_threadpool`）
- [ ] 查询是否分页/有索引；外部 API 调用是否有超时/重试
- [ ] 异常是否转换为 HTTPException，错误信息是否外泄内部细节
- [ ] 新增表是否符合 `dim_/ods_/dwd_/dws_` 命名
- [ ] 是否补充了测试
- [ ] `request_id` 是否在日志和任务表中透传

---

## 11. 部署注意（合入 main 后）

- 部署机器为 Windows，重启用根目录 `restart-all.cmd`（会重启后端 + 前端）。
- Python 与 ERP 部署在同一台机器（`127.0.0.1:8010`）。
- **内部 token 必须两端一致**：Python `.env` 的 `PYTHON_INTERNAL_API_TOKEN` = ERP 环境变量 `PYTHON_INTERNAL_API_TOKEN`。
- 改完 `.env` 需要重启 Python（`--reload` 不监听 `.env`）。
