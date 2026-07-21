# JMH ERP Python 数据服务

面向 Java ERP 的独立 Python 数据处理服务，当前实现外汇退税业务，并为后续财务
数据清洗、分析和报表模块保留扩展边界。

技术架构：FastAPI + RESTful + 任务型 API + MySQL。项目不再包含 Flask 页面或旧同步接口。

## 启动

```powershell
.\.venv\Scripts\python.exe app.py
```

指定端口：

```powershell
$env:PORT=5001
.\.venv\Scripts\python.exe app.py
```

- Swagger：`http://127.0.0.1:5000/docs`
- ReDoc：`http://127.0.0.1:5000/redoc`
- OpenAPI：`http://127.0.0.1:5000/openapi.json`
- 简易测试页面：`http://127.0.0.1:5000/test-ui`

## ERP 正式接口

耗时写操作统一创建任务：

```http
POST /api/v1/tasks
GET  /api/v1/tasks/{task_id}
GET  /api/v1/tasks
```

数据通过资源接口查询：

```http
GET /api/v1/customs-material-items
GET /api/v1/export-details
GET /api/v1/purchase-inventory
GET /api/v1/refund-generations
GET /api/v1/inventory-allocations
GET /api/v1/forex-receivables
POST /api/v1/export-details/export
POST /api/v1/purchase-inventory/export
POST /api/v1/forex-receivables/export
```

三个 `POST .../export` 接口均支持 `{"ids":[1,2]}` 导出选中数据，以及 `{"ids":null}` 导出全部有效数据，响应为 `.xlsx` 文件流。

当前任务类型：

- `CUSTOMS_MATERIAL_IMPORT`
- `CUSTOMS_DECLARATION_IMPORT`
- `PURCHASE_INVOICE_IMPORT`
- `FOREX_IMPORT`
- `REFUND_PACKAGE_GENERATE`
- `REFUND_PACKAGE_REVERSE`

完整请求和响应说明见 [`docs/ERP_API_INTEGRATION.md`](docs/ERP_API_INTEGRATION.md)。

## 当前退税业务关系

1. 先上传报关资料 `.xlsx`，保存合同下的报关商品。
2. 上传报关单 `.pdf`，按“合同协议号 + 标准化项号”匹配并形成完整出口明细。
3. 上传进货发票 `.pdf`，按发票号增量保存进货库存。
4. 上传外汇 `.xlsx`，只解析 `Sheet1`，按报关单号增量保存。
5. 汇总任务按 `SKU + 供应商` 在事务内 FIFO 预占库存，可跨多张发票，再生成最终文件夹并确认扣减。
6. 失败任务自动释放预占；冲销任务返还库存并保留完整扣减与冲销流水。

## 模块边界

- `app.py`：FastAPI 应用装配、全局异常和上传限制。
- `api/`：RESTful 路由，只负责协议转换和调用服务。
- `schemas/`：Pydantic 请求、响应和字段校验。
- `services/`：解析、匹配、导入及任务编排。
- `models/`：MySQL 数据访问。
- `tax_refund/`：退税领域的匹配、计算和文件生成。
- `sql/`：数据库初始化及增量迁移。
- `tests/`：业务和 API 回归测试。

## 后续模块扩展

新增财务模块时，不要把逻辑直接写进 `api/v1_router.py`。建议按领域增加：

```text
api/finance_router.py
schemas/finance.py
services/finance/
models/finance_*.py
sql/<date>_finance_*.sql
tests/test_finance_*.py
```

短查询使用 RESTful 资源接口，例如 `GET /api/v1/finance/transactions`；Excel 导入、
大批量清洗和报表生成继续创建 `/api/v1/tasks` 任务，只需增加任务类型及对应处理器。
这样 Java ERP 的调用模式保持不变。
