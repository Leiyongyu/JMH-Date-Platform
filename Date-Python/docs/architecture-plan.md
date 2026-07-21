# JMH Python 数据服务 — 架构方案与实施记录 v3

> 方向稿，不是一次性全面实施的计划。
> 核心原则：**模块化单体 + 垂直领域切片 + 渐进式改进**。

## 实施记录

### 2026-07-21：退税库存 FIFO、审计流水与任务统一

- 保留 `purchase_inventory` 作为发票库存批次，新增 `reserved_quantity`、版本号和最近扣减任务字段。
- 新增 `refund_generation`，记录退税文件生成任务、ERP 操作人、输出目录和生命周期。
- 新增不可物理删除的 `refund_inventory_allocation`，记录预占、正式扣减、释放和冲销关联的报关单与进货发票。
- `REFUND_PACKAGE_GENERATE` 改为事务预占 → 临时目录生成 → 正式扣减 → 原子发布目录。
- 新增 `REFUND_PACKAGE_REVERSE`。冲销保留原扣减记录并新增 `REVERSAL` 流水。
- 进货发票已有预占或扣减时，禁止覆盖日期、供应商、SKU、单位和采购数量。
- 删除退税模块私有线程池，所有处理器统一通过 `infrastructure.task_queue` 注册和执行。
- ERP 操作人由 `X-ERP-User-Id`、`X-ERP-User-Name` 传入，生成批次和流水保存 ID 与姓名快照。
- 新增 `GET /refund-generations`、`GET /inventory-allocations` 和增量脚本 `sql/20260721_refund_inventory_allocation.sql`。

### 2026-07-16 下午
- 企业收汇情况表：新增模板 + `_write_enterprise_receipt` 方法 + 汇总版收汇情况表
- 关联号兜底匹配：SKU 为空时走 `relation_no` 匹配，进货金额不拆分（旧数据兼容）
- 进货表新增字段：`declaration_month`, `declaration_batch`, `sequence_no`, `relation_no`
- 测试页面：多选 + 全选所有页 + 进货表税率/税额/单位列
- 输出目录加时间戳：每次生成到 `汇总_{YYYYMMDD_HHMMSS}`

### 2026-07-16 上午：企业收汇情况表
- 新增模板 `modules/tax_refund/templates/enterprise_receipt_template.xlsx`
- `workflow.py` 新增 `_write_enterprise_receipt` 方法，汇总所有供货方数据
- REFUND_PACKAGE_GENERATE 任务输出增加 `企业收汇情况表.xlsx`

### 2026-07-16：阶段 1+2+3 基础设施落地

**已创建的文件（18 个）**：

| 文件 | 用途 |
|------|------|
| `core/config.py` | 配置管理（环境变量 + .env 手动解析） |
| `core/logging.py` | 结构化日志（标准库 logging） |
| `core/errors.py` | 6 种业务异常子类 |
| `core/middleware.py` | RequestID + AccessLog + 四个异常 handler |
| `infrastructure/database.py` | mysql-connector-python 连接池（pool_size=5） |
| `infrastructure/task_queue.py` | 任务队列（幂等/重试/心跳/租约/服务恢复） |
| `infrastructure/file_storage.py` | 文件上传 + SHA256 + 幂等键 |
| `modules/tax_refund/repository.py` | 统一数据访问层（6 个查询函数） |
| `modules/tax_refund/parsers/__init__.py` | 解析器桥接 |
| `modules/tax_refund/schemas.py` | Schema 桥接 |
| `modules/tax_refund/task_handlers.py` | 任务处理器注册入口 |
| `.env.example` + `.env` + `.gitignore` | 环境管理 |
| `migrations/env.py` + `versions/001_baseline.py` + `versions/002_task_reliability.py` | Alembic |
| `alembic.ini` | Alembic 配置 |

**数据库变更**：
- `api_task` 表新增 7 个字段：`idempotency_key`, `retry_count`, `max_retries`, `next_retry_at`, `worker_id`, `heartbeat_at`, `lease_expires_at`
- 新增 2 个索引：`idx_api_task_idempotency`, `idx_api_task_recovery`

**API 兼容性**：所有现有路径不变，服务正常运行。`/docs`、`/test-ui`、`/api/v1/tasks` 均可用。

**已删除的旧目录**：`api/` `services/` `schemas/` `tax_refund/` `src/`
**保留的旧目录**：`models/`（通过 `models/base.py` 桥接到新连接池）

**已知限制**：
- Python 3.14 预发布版不兼容 pydantic-settings/structlog/SQLAlchemy/pytest 的 C 扩展
- 待 Python 稳定后升级到规划的技术栈
- `models/` 待 repository.py 功能完整后删除

---

## 1. 实际结构（2026-07-16 实施后）

```
Date-Python/
├── app.py                            # FastAPI 入口（带 lifespan、中间件、异常处理）
├── requirements.txt                  # 更新依赖
├── .env                              # 环境变量（密码，不提交）
├── .env.example                      # 环境变量模板
├── .gitignore                        # 含 .env 排除
│
├── core/                             # 应用内核（改名自 app/，避免与 app.py 冲突）
│   ├── config.py                     # os.environ + 手动 .env 解析（Python 3.14 稳定后换 pydantic-settings）
│   ├── logging.py                    # 标准库 logging（稳定后换 structlog）
│   ├── errors.py                     # 异常层次结构（AppError 基类 + 7 子类）
│   ├── middleware.py                  # RequestID + AccessLog + 统一异常处理
│   └── api/v1/
│       ├── tasks.py                  # 任务路由占位（当前委托给旧 api/v1_router.py）
│       └── resources.py              # 资源路由占位
│
├── modules/                          # 业务模块（垂直切片）
│   ├── tax_refund/
│   │   ├── repository.py             # ✅ 数据访问层（连接池，替换旧 models/*.py 裸 SQL）
│   │   ├── inventory_service.py      # ✅ FIFO预占、确认、释放、冲销及审计查询
│   │   ├── workflow.py               # ✅ 退税文件生成编排
│   │   ├── schemas.py                # FastAPI/Pydantic 请求响应模型
│   │   ├── task_handlers.py          # ✅ 统一任务队列处理器注册入口
│   │   └── parsers/__init__.py       # 桥接到旧 services/*.py 解析器
│   ├── finance/                      # 预留
│   ├── data_cleaning/                # 预留
│   └── reports/                      # 预留
│
├── infrastructure/                   # 基础设施
│   ├── database.py                   # ✅ mysql-connector-python 原生连接池（pool_size=5）
│   ├── task_queue.py                 # ✅ ThreadPoolExecutor + 幂等/重试/心跳/恢复
│   └── file_storage.py               # ✅ 文件上传 + SHA256 + 幂等键生成
│
├── migrations/                       # Alembic（Python 3.14 稳定后启用）
│   ├── env.py
│   └── versions/
│       ├── 001_baseline.py           # 基线（不做 DDL）
│       └── 002_task_reliability.py   # 任务可靠性字段
│
├── api/                              # 保留：旧路由（api/v1_router.py）
├── services/                         # 保留：旧解析器（逐步迁移到 modules/tax_refund/parsers/）
├── models/                           # 保留：旧数据访问（逐步迁移到 modules/tax_refund/repository.py）
├── schemas/                          # 保留：旧 Pydantic schemas
├── tax_refund/                       # 保留：旧退税工作流
├── sql/                              # 保留：原始 DDL + 增量脚本
├── tests/                            # 保留：旧测试
│
├── docs/                             # 架构文档
├── scripts/                          # 运维脚本（预留）
├── templates/                        # Excel 模板
├── test_ui/                          # 简易测试页面
├── uploads/                          # 文件上传目录
├── logs/                             # 运行日志
└── outputs/                          # 退税输出目录
```

### 与 v2 规划的主要差异

| 规划 | 实际 | 原因 |
|------|------|------|
| `app/` 目录 | `core/` 目录 | `app.py` 和 `app/` 在同一目录导致 Python 导入冲突 |
| pydantic-settings | os.environ + 手动 .env | Python 3.14 预发布版不兼容 pydantic-settings C 扩展 |
| structlog | 标准库 logging | Python 3.14 兼容性问题 |
| SQLAlchemy + asyncmy | mysql-connector-python 原生连接池 | Python 3.14 兼容性问题 |
| 全部文件新建后删旧 | 新旧共存，桥接导入 | 渐进式迁移，降低风险 |

---

## 2. API 路径策略

### 现有路径永久保留，不做重定向

| 方法 | 路径 | 状态 |
|------|------|------|
| `POST` | `/api/v1/tasks` | 保持 |
| `GET` | `/api/v1/tasks/{id}` | 保持 |
| `GET` | `/api/v1/tasks` | 保持 |
| `GET` | `/api/v1/customs-material-items` | 保持 |
| `GET` | `/api/v1/export-details` | 保持 |
| `POST` | `/api/v1/export-details/export` | 出口明细 Excel 导出（选中/全部） |
| `GET` | `/api/v1/purchase-inventory` | 保持 |
| `POST` | `/api/v1/purchase-inventory/export` | 进货明细 Excel 导出（选中/全部） |
| `GET` | `/api/v1/refund-generations` | 新增：生成批次审计 |
| `GET` | `/api/v1/inventory-allocations` | 新增：库存扣减流水 |
| `GET` | `/api/v1/forex-receivables` | 保持 |
| `POST` | `/api/v1/forex-receivables/export` | 回款汇总 Excel 导出（选中/全部） |

**新模块**使用领域前缀，不与现有路径冲突：

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/api/v1/finance/customs-test` | 报货测试（示例） |
| `GET` | `/api/v1/finance/reports/*` | 报表查询（示例） |

**为什么不用 301/302**：
- 部分 HTTP 客户端对 POST 重定向行为不一致（可能变成 GET）
- Java `HttpClient` 默认不自动跟随重定向
- 永远不为了"架构美观"破坏已有 API 契约

---

## 3. 技术决策（逐项说明）

### 3.1 数据库：mysql-connector-python 连接池 + Repository/Service 层

| 维度 | 当前实现 | 远期选择 |
|------|----------|----------|
| 连接 | `MySQLConnectionPool`，默认 pool_size=5 | 并发量增长后再评估 SQLAlchemy |
| 查询 | 新功能集中在模块 Repository/Service；旧 `models/` 渐进迁移 | 完成旧模型清理 |
| 迁移 | `sql/init_database.sql` + 日期命名增量脚本 | Python 版本稳定后启用 Alembic |
| 事务 | mysql-connector 显式 `start_transaction/commit/rollback` | 保持清晰事务边界 |

**为什么不用异步**：
- Excel 解析、PDF 提取、FIFO 计算都是同步 CPU 密集型
- 异步 ORM 需要全链路重写（model/service/task 全部得改）
- 线程池执行 `ThreadPoolExecutor` 搭配同步 Session 简单可靠
- 将来真有高并发 I/O 场景，可以局部引入 `AsyncSession`，不必一步到位

**事务服务示例**：
```python
# modules/tax_refund/inventory_service.py
conn = get_conn()
conn.start_transaction()
cursor.execute("SELECT ... FROM purchase_inventory ... FOR UPDATE")
# 校验 FIFO 后执行预占并写审计流水
conn.commit()
```

### 3.2 配置：pydantic-settings，密码无默认值

```python
# app/core/config.py
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JMH_", env_file=".env")

    # 数据库 — 密码不允许有默认值
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: SecretStr           # 必填，无默认值
    db_name: str = "export_tax_refund"
    db_pool_size: int = 5
    db_pool_overflow: int = 10

    # 第二个库（只读）
    jmh_db_host: str = "localhost"
    jmh_db_port: int = 3306
    jmh_db_user: str = "root"
    jmh_db_password: SecretStr       # 必填
    jmh_db_name: str = "jmh_data_platform"

    upload_dir: Path = Path("uploads")
    max_upload_mb: int = 50
    task_max_workers: int = 4        # 线程池大小

    log_level: str = "INFO"
    log_format: str = "console"      # "console" | "json"
```

开发环境创建 `.env`：
```
JMH_DB_PASSWORD=1qaz!QAZ
JMH_JMH_DB_PASSWORD=1qaz!QAZ
```

`.gitignore` 必须包含 `.env`，不得提交。

### 3.3 任务可靠性

当前任务统一由 `infrastructure.task_queue.ThreadPoolTaskQueue` 执行，领域模块只注册处理器：

```python
# infrastructure/task_queue.py

class TaskQueue(ABC):
    """后台任务队列抽象。开发用线程池，生产可切换 Redis Queue。"""
    @abstractmethod
    def enqueue(self, task_id: int) -> None: ...
    @abstractmethod
    def cancel(self, task_id: int) -> bool: ...
    @abstractmethod
    def recover(self) -> list[int]: ...
    """服务重启后，把 PENDING/RUNNING 任务重新入队"""


class ThreadPoolTaskQueue(TaskQueue):
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: dict[int, Future] = {}

    def enqueue(self, task_id):
        # 1. 把 api_task 状态更新为 RUNNING
        # 2. 提交到线程池
        # 3. 完成后写 SUCCESS/FAILED
        ...

    def cancel(self, task_id):
        future = self._futures.get(task_id)
        if future and not future.done():
            return future.cancel()
        return False

    def recover(self):
        """从 api_task 表找出所有 PENDING/RUNNING 且未超时的任务，重新入队"""
        ...
```

**`api_task` 表需要补充的字段**（Alembic 增量迁移）：

| 字段 | 类型 | 用途 |
|------|------|------|
| `idempotency_key` | `CHAR(64)` | 幂等键（file_sha256 + task_type），防重复提交 |
| `retry_count` | `INT DEFAULT 0` | 已重试次数 |
| `max_retries` | `INT DEFAULT 0` | 最大重试次数 |
| `next_retry_at` | `DATETIME(3)` | 下次重试时间 |
| `worker_id` | `VARCHAR(64)` | 执行该任务的 worker 标识 |
| `heartbeat_at` | `DATETIME(3)` | Worker 最后心跳时间 |
| `lease_expires_at` | `DATETIME(3)` | 任务租约过期时间 |

**任务状态机**：

```
PENDING ──→ RUNNING ──→ SUCCESS
    │          │
    │          ├──→ FAILED ──→ PENDING (retry_count < max_retries)
    │          │
    │          └──→ FAILED (terminal, retry_count >= max_retries)
    │
    └──→ CANCELLED
```

**服务重启恢复**：
- `app.py` 启动时调用 `task_queue.recover()`
- 把 `RUNNING` 且 `lease_expires_at < NOW()` 的任务重置为 `PENDING`
- 把 `PENDING` 任务重新入队

**文件重复上传**：
- 创建任务时先查 `idempotency_key = SHA256(file + task_type)`
- 如果已存在 SUCCESS 任务 → 直接返回已有任务 ID（幂等）
- 如果已存在 RUNNING/PENDING → 返回已有任务 ID + 状态

### 3.4 任务与新模块的关系

**不**为新模块单独建任务状态表。`api_task` 是所有异步任务的统一入口。

```
api_task (统一)
  ├── id, task_type, task_status, progress, error_message
  ├── idempotency_key, retry_count, worker_id, heartbeat
  ├── request_payload (JSON)  ← 领域参数
  └── result_payload  (JSON)  ← 领域结果

领域结果表（只存业务生命周期与审计，不替代统一任务状态机）
  ├── refund_generation      (api_task_id UNIQUE FK → api_task)
  ├── refund_inventory_allocation
  ├── customs_test_result    (api_task_id FK → api_task)
  ├── cleaning_job_result    (api_task_id FK → api_task)
  └── report_instance        (api_task_id FK → api_task)
```

### 3.5 退税库存一致性设计

库存恒等式：

```text
purchased_quantity = allocated_quantity + reserved_quantity + remaining_quantity
```

状态流：

```text
api_task: PENDING → RUNNING → SUCCESS/FAILED
refund_generation: PREPARING → RESERVED → FILE_PENDING → COMMITTED → REVERSED
                          └→ FAILED（预占全部释放）
```

核心规则：

1. 库存池使用 `sku_normalized + supplier_tax_no`，同一供应商内按发票日期 FIFO，可跨多张发票。
2. 事务使用 `SELECT ... FOR UPDATE` 锁定出口和库存；锁后再次校验数量与 FIFO 顺序。
3. 文件生成期间只增加 `reserved_quantity`，失败时返还 `remaining_quantity`。
4. 文件生成完成后把预占转为 `allocated_quantity`，生成批次进入 `FILE_PENDING`。
5. 临时目录原子发布成功后进入 `COMMITTED`；发布失败由同一任务重试，不再次扣库存。
6. `refund_generation.api_task_id` 唯一；ERP 的 `Idempotency-Key` 防止网络重试创建重复任务。
7. 冲销不删除原流水，新增 `REVERSAL` 流水并返还库存。
8. 流水保存报关单、发票、SKU、操作人快照，源数据后续变化不影响历史审计。

### 3.6 日志：structlog

```python
# app/core/logging.py
import structlog

def setup_logging(level: str, format_: str):
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer() if format_ == "console"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

# 使用
logger = structlog.get_logger()
logger.info("task_started", task_id=123, task_type="FOREX_IMPORT")
```

### 3.7 异常层次结构

```python
# app/core/errors.py

class AppError(Exception):
    """基类：所有已知异常"""
    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"

class BadRequestError(AppError):
    http_status = 400; error_code = "BAD_REQUEST"

class ValidationError(AppError):
    http_status = 422; error_code = "VALIDATION_ERROR"

class NotFoundError(AppError):
    http_status = 404; error_code = "NOT_FOUND"

class TaskError(AppError):
    """任务执行失败（可重试）"""
    http_status = 400; error_code = "TASK_FAILED"

class FileError(AppError):
    http_status = 422; error_code = "FILE_ERROR"

class DuplicateFileError(FileError):
    http_status = 409; error_code = "DUPLICATE_FILE"
```

中间件统一捕获：
```python
# app.py 中注册
@app.exception_handler(AppError)
async def handle_app_error(request, exc: AppError):
    return JSONResponse(
        {"success": False, "error": {"code": exc.error_code, "message": str(exc)}},
        status_code=exc.http_status,
    )
```

### 3.8 Java/Vue 不在本项目范围

本项目只负责 Python 端。与 Java/Vue 的对接通过 OpenAPI 文档（`/docs`、`/openapi.json`）交付：

- Java 端需要新增 Controller → 提供接口说明和示例请求
- Vue 端需要新增页面 → 提供接口说明和示例请求
- **不直接修改其他两个工程的代码**

---

## 4. 数据库迁移策略（Alembic）

### 4.1 建立基线（Baseline）

已有数据库不能直接执行 `alembic upgrade head`。

**步骤**：

```bash
# 1. 备份现有数据库
mysqldump -u root -p export_tax_refund > backup_$(date +%Y%m%d).sql

# 2. 从现有数据库导出实际表结构
# 省去 AUTO_INCREMENT 和随机值
mysqldump -u root -p --no-data --skip-add-drop-table export_tax_refund > current_schema.sql

# 3. 编写基线迁移，映照当前真实表结构
# migrations/versions/001_baseline.py

# 4. 对现有数据库标记基线版本
alembic stamp 001_baseline

# 5. 之后新增字段才用 alembic upgrade head
```

**`001_baseline.py` 是手动编写的**（映照 init_database.sql + 所有增量 SQL），不依赖 `alembic autogenerate`。

### 4.2 原始 SQL 文件保留

`sql/` 目录不删除。其中：
- `init_database.sql` — 保留为参考，不再用作建库入口
- 增量 SQL — 保留备查
- 新增的迁移 SQL — 全部写在 Alembic versions 中

---

## 5. 数据清洗模块安全设计

### 不允许动态表名/列名

不建 `target_table`、`target_column` 这种字段让用户任意指定。

**改为数据集注册表**：

```python
# modules/data_cleaning/datasets.py
DATASETS = {
    "export_detail": {
        "table": "export_detail",
        "columns": ["export_product_name", "sku_original", "contract_no", ...],
        "key_column": "id",
        "readonly": False,
    },
    "purchase_inventory": {
        "table": "purchase_inventory",
        "columns": ["product_name", "sku_normalized", ...],
        "key_column": "id",
        "readonly": False,
    },
}
```

### 清洗安全规则

```
原始数据 → 清洗预览（显示影响行数） → 用户确认 → 写入清洗层
                                              └── 原始数据不直接覆盖
```

- 清洗规则版本化（`rule_version`）
- 执行前预览影响行数
- 清洗结果写入独立的清洗批次表，记录原始值和新值
- 所有清洗操作通过绑定参数执行，不拼接 SQL 值
- 数据库账号仅授予 INSERT/SELECT 权限给清洗表

### 清洗表设计

```sql
-- 清洗规则（代码定义，DB 只存执行记录）
CREATE TABLE cleaning_rule (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    rule_name VARCHAR(100) UNIQUE NOT NULL,
    module VARCHAR(50) NOT NULL,         -- 对应代码中的注册名
    rule_type VARCHAR(50) NOT NULL,      -- TRIM / UPPER / REGEX_REPLACE 等
    config JSON NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    version INT DEFAULT 1,
    created_at DATETIME(3)
);

-- 清洗执行记录（通过 api_task_id 关联统一任务）
CREATE TABLE cleaning_job (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    api_task_id BIGINT NOT NULL,
    rule_id BIGINT NOT NULL,
    dataset_name VARCHAR(100) NOT NULL,
    affected_rows INT DEFAULT 0,
    error_rows INT DEFAULT 0,
    preview_data JSON,                  -- 前100行变更预览
    started_at DATETIME(3),
    completed_at DATETIME(3),
    FOREIGN KEY (api_task_id) REFERENCES api_task(id)
);

-- 清洗明细（变更追踪）
CREATE TABLE cleaning_detail (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    job_id BIGINT NOT NULL,
    record_id BIGINT NOT NULL,          -- 被清洗记录的主键
    column_name VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    FOREIGN KEY (job_id) REFERENCES cleaning_job(id)
);
```

---

## 6. 报表模块安全设计

### 不在数据库中存储 SQL 模板

报表查询定义放在代码中并版本控制：

```python
# modules/reports/definitions.py
REPORTS = {
    "monthly_export_summary": {
        "name": "月度出口汇总",
        "sql": """
            SELECT declaration_month, COUNT(*) as cnt, SUM(fob_amount) as total
            FROM export_detail
            WHERE is_deleted=0 AND declaration_month=:month
            GROUP BY declaration_month
        """,
        "params": {"month": "202601"},
        "allowed_sort_columns": ["cnt", "total", "declaration_month"],
        "export_formats": ["xlsx", "csv"],
    },
}
```

### 安全规则

- 所有参数使用绑定变量（`:month`），不拼接 SQL 值
- 排序字段和表名使用白名单
- 报表数据库账号仅 SELECT 权限
- 大结果集写入文件，不在 JSON 字段存储数据

### 报表实例表

```sql
CREATE TABLE report_instance (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    api_task_id BIGINT NOT NULL,
    report_name VARCHAR(100) NOT NULL,
    params_used JSON,
    file_path VARCHAR(1000),           -- 生成的文件路径
    file_hash CHAR(64),
    row_count INT,
    file_size_bytes BIGINT,
    generated_at DATETIME(3),
    expires_at DATETIME(3),
    FOREIGN KEY (api_task_id) REFERENCES api_task(id)
);
```

---

## 7. 报货测试模块（待业务确认）

以下为方向性描述，表和字段需要在业务确认后再定：

### 假设的业务场景
在正式上传报关单之前，对报关资料做预检查：
1. PDF 报关单 vs Excel 报关资料的一致性
2. SKU 是否能匹配到进货库存
3. 金额、数量差异超出容差范围的条目
4. 外汇记录是否覆盖所有报关单

### 不提前建表

业务字段、输入文件格式、校验规则、结果输出格式都未确认前，不创建任何表。等业务方确认后，在新架构下作为第一个验证模块开发。

---

## 8. 实施顺序（5 个阶段）

### 阶段 1：基础设施（不改业务，不改接口）

- [ ] `app/core/config.py` — pydantic-settings（密码用 SecretStr + .env）
- [ ] `app/core/logging.py` — structlog 配置
- [ ] `app/core/errors.py` — 异常层次结构
- [ ] `infrastructure/database.py` — SQLAlchemy 同步 Engine + QueuePool
- [ ] 中间件 — request_id + 统一异常处理 + 访问日志
- [ ] `.gitignore` 确保 `.env` 不被提交

**产出**：旧代码继续工作，新基础设施并行存在。

### 阶段 2：任务可靠性与 Repository

- [x] `infrastructure/task_queue.py` — 线程池实现 + 幂等/重试/恢复
- [ ] `api_task` 表增加可靠性字段（Alembic 增量迁移）
- [ ] `modules/tax_refund/repository.py` — 替换 `models/*.py` 中的裸 SQL
- [ ] Service 层通过 Repository 获取数据

**产出**：任务不再丢失，连接池生效，数据访问有统一入口。

### 阶段 3：Alembic 基线与退税模块整理

- [ ] `migrations/versions/001_baseline.py` — 映照当前表结构
- [ ] 对现有数据库 `alembic stamp 001_baseline`
- [x] `sql/20260716_task_reliability.sql` — 加幂等/重试字段
- [x] `sql/20260721_refund_inventory_allocation.sql` — 库存预占、流水和冲销
- [ ] 将 `services/*.py` 迁移到 `modules/tax_refund/parsers/`
- [ ] 将 `api/v1_router.py` 拆为 `app/api/v1/tasks.py` + `app/api/v1/resources.py`
- [ ] 路径完全不变，只做代码位置整理

### 阶段 4：开发第一个新模块

- [ ] 与业务方确认报货测试或数据清洗的具体需求
- [ ] 按 `modules/<name>/` 模板开发
- [ ] 验证路由、Repository、任务队列、异常处理是否流畅
- [ ] 根据实际开发体验调整模块模板

### 阶段 5：Redis Worker + 报表平台

- [ ] 按需将任务队列切换到 Redis + 独立 Worker
- [ ] 报表模块引入只读副本连接
- [ ] 大报表异步生成 + 文件下载

---

## 9. 关键原则总结

1. **API 路径永久保留**，不做重定向
2. **SQLAlchemy 先同步 + 连接池**，不急异步
3. **模块化单体**，垂直切片，不搞完整 DDD
4. **Alembic 先 baseline**，不替代现有 SQL
5. **配置密码无默认值**，用 SecretStr + .env
6. **任务系统补齐幂等、重试、心跳、恢复**
7. **api_task 是唯一任务状态机**，领域表不重复
8. **数据清洗禁止任意 SQL**，用注册表 + 白名单
9. **报表 SQL 放代码里版本化**，不存数据库
10. **Java/Vue 不在本项目范围**，只输出 OpenAPI 对接文档
