# JMH Python 数据服务 — ERP API 对接文档

版本：v1.2 | 基础地址：`http://<python-host>:5000/api/v1` | 框架：FastAPI

---

## 1. 接口设计

- 耗时写操作（上传、解析、匹配、入库、汇总生成）统一通过 `POST /tasks` 创建异步任务，返回 `task_id` 后轮询 `GET /tasks/{id}` 获取进度和结果。
- 已入库数据通过资源型接口分页查询。
- Java ERP 使用 `X-ERP-User-Id` 和 `X-ERP-User-Name` 传递操作人。姓名包含中文时，必须先按 UTF-8 做 URL 百分号编码；Python 接收后自动解码。旧的 `X-ERP-User` 仅保留兼容。
- 退税生成和冲销建议传 `Idempotency-Key`，同一个键的重复请求返回同一任务，不重复扣库存。
- 所有接口返回统一 JSON 格式，金额用字符串防精度丢失，日期为 ISO 8601。

Swagger：`http://<python-host>:5000/docs`

---

## 2. 接口总览

### 任务型（异步）

| # | 方法 | Content-Type | task_type | 说明 |
|---|------|-------------|-----------|------|
| 1 | `POST /tasks` | multipart/form-data | `CUSTOMS_MATERIAL_IMPORT` | 报关资料 Excel 导入 |
| 2 | `POST /tasks` | multipart/form-data | `CUSTOMS_DECLARATION_IMPORT` | 报关单 PDF 导入 |
| 3 | `POST /tasks` | multipart/form-data | `PURCHASE_INVOICE_IMPORT` | 进货发票 PDF 导入 |
| 4 | `POST /tasks` | multipart/form-data | `FOREX_IMPORT` | 外汇回款 Excel 导入 |
| 5 | `POST /tasks` | application/json | `REFUND_PACKAGE_GENERATE` | 退税汇总资料生成 |
| 6 | `POST /tasks` | application/json | `REFUND_PACKAGE_REVERSE` | 冲销已完成的退税库存扣减 |
| 7 | `GET /tasks/{id}` | — | — | 查询任务状态与结果 |
| 8 | `GET /tasks` | — | — | 分页查询任务历史 |

### 查询型（同步）

| # | 方法 | 说明 |
|---|------|------|
| 9 | `GET /customs-material-items` | 报关资料商品查询 |
| 10 | `GET /export-details` | 出口明细分页查询 |
| 11 | `GET /purchase-inventory` | 进货库存分页查询 |
| 12 | `GET /refund-generations` | 退税文件生成批次查询 |
| 13 | `GET /inventory-allocations` | 库存预占、扣减和冲销流水查询 |
| 14 | `GET /forex-receivables` | 外汇应收分页查询 |
| 15 | `POST /export-details/export` | 导出选中或全部出口明细 Excel |
| 16 | `POST /purchase-inventory/export` | 导出选中或全部进货明细 Excel |
| 17 | `POST /forex-receivables/export` | 导出选中或全部回款汇总 Excel |

---

## 3. 通用响应

### 成功
```json
{
  "success": true,
  "data": {},
  "meta": {"page": 1, "page_size": 50, "total": 120, "total_pages": 3}
}
```

### 任务创建（单文件）(HTTP 202)
```json
{
  "success": true,
  "data": {
    "id": 81,
    "task_type": "FOREX_IMPORT",
    "task_status": "PENDING",
    "status_url": "/api/v1/tasks/81"
  }
}
```

### 任务创建（多文件）(HTTP 202)
```json
{
  "success": true,
  "data": {
    "task_ids": [82, 83, 84],
    "count": 3,
    "task_type": "PURCHASE_INVOICE_IMPORT",
    "task_status": "PENDING",
    "status_url": "/api/v1/tasks/84"
  }
}
```

### 失败
```json
{
  "success": false,
  "error": {
    "code": "INVALID_FILE_TYPE",
    "message": "FOREX_IMPORT 仅支持 .xlsx 文件"
  }
}
```

### HTTP 状态码

| 码 | 含义 |
|----|------|
| 200 | 查询成功 |
| 202 | 异步任务已接收 |
| 400 | 请求参数不合法 |
| 404 | 资源不存在 |
| 409 | 文件重复上传 |
| 413 | 文件超过 50 MB |
| 422 | 业务校验不通过 |
| 500 | 服务端内部错误 |

---

## 4. 任务型接口

### 4.1 报关资料 Excel 导入

上传历史报关资料 Excel，按合同协议号保存版本。同合同新文件上传时旧版本自动归档。**支持多文件上传**。

```http
POST /api/v1/tasks
Content-Type: multipart/form-data
X-ERP-User-Id: 10086
X-ERP-User-Name: %E5%BC%A0%E4%B8%89
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_type` | string | ✅ | `CUSTOMS_MATERIAL_IMPORT` |
| `file` | file(.xlsx) | ✅ | 最大 50 MB，可传多个 |

---

### 4.2 报关单 PDF 导入

解析报关单 PDF，按合同协议号 + 项号匹配已导入的报关资料，形成完整出口明细并入库。

```http
POST /api/v1/tasks
Content-Type: multipart/form-data
X-ERP-User-Id: 10086
X-ERP-User-Name: %E5%BC%A0%E4%B8%89
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_type` | string | ✅ | `CUSTOMS_DECLARATION_IMPORT` |
| `file` | file(.pdf) | ✅ | PDF 标题须含"中华人民共和国海关出口货物报关单"，可传多个 |
| `declaration_month` | string | ❌ | 申报年月 `YYYYMM`，不填则从报关单推断 |
| `declaration_batch` | string | ❌ | 申报批次（1~3位数字），填了则生成关联号，不填仅生成序号 |
| `export_date` | string | ❌ | 统一出口日期 `YYYY-MM-DD`，覆盖 PDF 中各商品日期 |

**前置条件**: 对应合同的报关资料 Excel 须先导入。

**处理逻辑**: 解析 PDF → 提取报关单头 + 商品表 → 按合同号 + 标准化项号匹配报关资料 Excel → 将报关单号转换为“18位基础编号 + 3位商品项号” → 自动生成序号（00000001 起）→ upsert 到 `export_detail`。因此 `export_detail.customs_declaration_no` 从入库时就是21位，第1项结尾为 `001`、第2项为 `002`。

---

### 4.3 进货发票 PDF 导入

解析增值税专用发票 PDF，增量保存进货库存。

```http
POST /api/v1/tasks
Content-Type: multipart/form-data
X-ERP-User-Id: 10086
X-ERP-User-Name: %E5%BC%A0%E4%B8%89
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_type` | string | ✅ | `PURCHASE_INVOICE_IMPORT` |
| `file` | file(.pdf) | ✅ | 电子发票 PDF |
| `declaration_month` | string | ❌ | 申报年月 `YYYYMM` |
| `declaration_batch` | string | ❌ | 申报批次，填了则生成关联号回写进货表 |

**处理逻辑**: 解析 PDF → 提取发票头 + 商品行 → 按发票号 + 项号 upsert → 每发票独立序号 → 有批次时自动生成关联号。库存已经预占或扣减后，再上传同一发票只允许更新来源和解析信息；发票日期、供应商税号、SKU、单位或采购数量发生变化时任务失败，必须先冲销或走库存调整。

---

### 4.4 外汇回款 Excel 导入

解析外汇回款汇总表 Sheet1，增量保存应收、回款及分配。

```http
POST /api/v1/tasks
Content-Type: multipart/form-data
X-ERP-User-Id: 10086
X-ERP-User-Name: %E5%BC%A0%E4%B8%89
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_type` | string | ✅ | `FOREX_IMPORT` |
| `file` | file(.xlsx) | ✅ | 仅解析 Sheet1，可传多个 |

**防重复**: 同 SHA256 文件自动跳过，返回已有批次 ID。

**处理逻辑**: 解析 Sheet1 → 拆分报关单号 → 预览校验 → 单事务写入 `forex_export_receivable` + `forex_receipt` + `forex_receipt_allocation`。

---

### 4.5 退税汇总资料生成

从数据库读取出口、进货、外汇数据，SKU/FIFO 匹配库存，生成四套申报文件。

```http
POST /api/v1/tasks
Content-Type: application/json
X-ERP-User-Id: 10086
X-ERP-User-Name: %E5%BC%A0%E4%B8%89
Idempotency-Key: refund-202601-erp-batch-001

{
  "task_type": "REFUND_PACKAGE_GENERATE",
  "output_parent_dir": "D:/JMH/退税输出",
  "declaration_month": "202601",
  "payer_name": "Hong Kong Cammy Yeson Limited",
  "overwrite": false,
  "export_ids": null
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `task_type` | string | ✅ | — | `REFUND_PACKAGE_GENERATE` |
| `output_parent_dir` | string | ✅ | — | Python 服务端可写目录的绝对路径 |
| `declaration_month` | string | ✅ | — | 6位申报年月 |
| `payer_name` | string | ❌ | `Hong Kong Cammy Yeson Limited` | 付汇人 |
| `overwrite` | bool | ❌ | `false` | 是否覆盖已有目录 |
| `export_ids` | int[] | ❌ | `null` | 指定尚未分配库存的出口明细 ID；不传时处理全部未分配且已匹配明细 |

**库存处理语义**：

1. 以 `SKU + 供应商税号` 作为库存池，按 `invoice_date → invoice_no → invoice_item_no → id` 严格 FIFO。
2. 一个出口数量可以跨同一供应商的多张发票扣减；任一出口库存不足时不做部分扣减。
3. 数据库事务内先把 `remaining_quantity` 转为 `reserved_quantity`。
4. 文件在临时目录成功生成后，再把预占转为 `allocated_quantity` 并写入不可删除的审计流水。
5. 生成失败自动释放预占；文件发布失败由同一任务重试，不会重复扣库存。
6. 只有最终目录发布成功，任务才返回 `SUCCESS`。

`export_detail` 入库时已将“出口货物报关单号”保存为原始18位报关单号拼接3位商品项号，例如第1项拼接 `001`、第2项拼接 `002`，最终长度为21位；生成申报文件时直接沿用并再次校验此规则。来源数据已经是21位时会先取前18位再拼接，避免重复项号。

任务结果新增 `generation_id`，用于查询本次生成记录和每条库存扣减流水。

**输出目录结构**:
```
{output_parent_dir}/汇总_{YYYYMMDD_HHMMSS}_{task_id}/
├── 001/                          ← 按供货方退税金额降序编号
│   ├── 《外贸企业出口退税进货明细申报表》导入模板-{纳税号}-001.xlsx
│   ├── 《外贸企业出口退税出口明细申报表》导入模板-{纳税号}-001.xlsx
│   └── 出口业务收汇情况表_{纳税号}_001.xlsx
├── 002/ ...
├── 出口业务收汇情况表_汇总.xlsx      ← 所有供货方合并
└── 企业收汇情况表.xlsx              ← 企业级汇总
```

---

### 4.6 退税库存冲销

冲销一个已经 `COMMITTED` 的退税生成批次。原扣减流水不会删除，系统新增 `REVERSAL` 流水并把数量退回可用库存。

```http
POST /api/v1/tasks
Content-Type: application/json
X-ERP-User-Id: 10086
X-ERP-User-Name: %E5%BC%A0%E4%B8%89
Idempotency-Key: reverse-generation-238

{
  "task_type": "REFUND_PACKAGE_REVERSE",
  "generation_id": 238,
  "reason": "报关资料作废，重新生成"
}
```

只有 `COMMITTED` 批次可以冲销。重复冲销同一批次不会重复返还库存。

---

## 5. 查询型接口

### 5.1 查询任务 `GET /tasks/{id}`

```http
GET /api/v1/tasks/81
```

**响应字段**: `id`, `task_type`, `task_status` (PENDING/RUNNING/SUCCESS/PARTIAL/FAILED), `progress_current`, `progress_total`, `request_payload`, `result_payload`, `error_message`, `original_file_name`, `created_by`, `started_at`, `completed_at`

---

### 5.2 任务历史 `GET /tasks`

```http
GET /api/v1/tasks?page=1&page_size=20&task_type=FOREX_IMPORT&task_status=SUCCESS
```

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页，最大 100 |
| `task_type` | string | — | 5 种类型之一 |
| `task_status` | string | — | PENDING / RUNNING / SUCCESS / PARTIAL / FAILED |

---

### 5.3 报关资料商品 `GET /customs-material-items`

```http
GET /api/v1/customs-material-items?contract_no=FBA15L7CCK57
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `contract_no` | string | ✅ | 合同协议号 |

返回当前有效版本（`is_current=1`）。

**返回字段**: `contract_agreement_no`, `product_sequence_no`, `commodity_code`, `product_name`, `sku`, `transaction_quantity`, `transaction_unit`, `unit_price`, `total_price`, `currency_code` 等。

---

### 5.4 出口明细 `GET /export-details`

```http
GET /api/v1/export-details?page=1&page_size=50&customs_declaration_no=531620260000035&declaration_month=202601&customs_match_status=MATCHED
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | ❌ | 页码，默认 1 |
| `page_size` | int | ❌ | 每页，默认 50，最大 100 |
| `contract_no` | string | ❌ | 合同协议号 |
| `customs_declaration_no` | string | ❌ | 报关单号，**前缀匹配**（18位匹配全部项号） |
| `declaration_month` | string | ❌ | 申报年月 |
| `declaration_batch` | string | ❌ | 申报批次 |
| `relation_no` | string | ❌ | 关联号 |
| `customs_match_status` | string | ❌ | MATCHED / UNMATCHED |

**返回字段**: `id`, `customs_declaration_no`, `contract_no`, `customs_item_no`, `sku_normalized`, `export_product_name`, `unit`, `export_quantity`, `fob_amount`, `export_date`, `customs_match_status`, `declaration_month`, `declaration_batch`, `sequence_no`, `relation_no` 等。

---

### 5.5 进货库存 `GET /purchase-inventory`

```http
GET /api/v1/purchase-inventory?page=1&page_size=50&supplier_tax_no=91330381563310053K&invoice_date_from=2026-01-01&inventory_status=AVAILABLE
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | ❌ | 页码，默认 1 |
| `page_size` | int | ❌ | 每页，默认 50，最大 100 |
| `invoice_no` | string | ❌ | 发票号 |
| `invoice_date_from` | string | ❌ | 开票日期起 `YYYY-MM-DD` |
| `invoice_date_to` | string | ❌ | 开票日期止 `YYYY-MM-DD` |
| `supplier_tax_no` | string | ❌ | 供货方纳税号 |
| `buyer_tax_no` | string | ❌ | 购买方纳税号 |
| `sku_normalized` | string | ❌ | 标准化 SKU |
| `inventory_status` | string | ❌ | AVAILABLE / PARTIAL / EXHAUSTED |

**返回字段**: `id`, `invoice_no`, `invoice_date`, `invoice_item_no`, `sku_normalized`, `product_name`, `unit`, `supplier_name`, `supplier_tax_no`, `purchased_quantity`, `allocated_quantity`, `reserved_quantity`, `remaining_quantity`, `unit_price`, `taxable_amount`, `tax_rate`, `tax_amount`, `inventory_status`, `last_allocated_at`, `last_allocation_task_id` 等。

---

### 5.6 退税生成批次 `GET /refund-generations`

```http
GET /api/v1/refund-generations?page=1&page_size=20&status=COMMITTED&declaration_month=202601&operator_id=10086
```

可选条件：`status`、`operator_id`、`declaration_month`。状态包括 `PREPARING`、`RESERVED`、`FILE_PENDING`、`COMMITTED`、`FAILED`、`REVERSED`。

主要返回字段：`id`、`api_task_id`、`declaration_month`、`output_directory`、`generation_status`、`generated_by_id`、`generated_by_name`、`generated_at`、`committed_at`、`reversed_at`、`result_payload`。

### 5.7 库存扣减流水 `GET /inventory-allocations`

```http
GET /api/v1/inventory-allocations?page=1&page_size=50&generation_id=238&sku_normalized=JMH70044-0741
```

可选条件：`generation_id`、`invoice_no`、`sku_normalized`、`customs_declaration_no`、`operator_id`、`entry_type`、`status`。

每条流水包含报关单、出口项、进货发票、SKU、操作前数量、分配/冲销数量、操作后数量、操作人 ID、操作人姓名和操作时间。`entry_type=ALLOCATION` 表示扣减，`entry_type=REVERSAL` 表示冲销返还。

---

### 5.8 外汇应收 `GET /forex-receivables`

```http
GET /api/v1/forex-receivables?page=1&page_size=50&customs_no=531620260000035&export_date_from=2026-01-01
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | ❌ | 页码，默认 1 |
| `page_size` | int | ❌ | 每页，默认 50，最大 100 |
| `customs_no` | string | ❌ | 报关单号 18 位 |
| `contract_no` | string | ❌ | 合同协议号 |
| `business_entity` | string | ❌ | 业务主体 |
| `source_type` | string | ❌ | 来源类型 |
| `export_date_from` | string | ❌ | 出口日期起 `YYYY-MM-DD` |
| `export_date_to` | string | ❌ | 出口日期止 `YYYY-MM-DD` |

**返回字段**: `id`, `customs_declaration_no`, `contract_no`, `business_entity`, `export_date`, `export_amount_usd`, `received_amount_usd`(已收汇金额), `monthly_exchange_rate`, `source_type` 等。

---

### 5.9 Excel 导出

三个导出接口使用相同请求结构：

| 接口 | 导出内容 |
|------|----------|
| `POST /export-details/export` | 出口明细 |
| `POST /purchase-inventory/export` | 进货明细及当前库存数量 |
| `POST /forex-receivables/export` | 报关单应收、分配回款及银行回款汇总 |

导出选中记录时传数据库主键：

```http
POST /api/v1/export-details/export
Content-Type: application/json

{"ids": [101, 102, 108]}
```

导出该资源的全部有效记录时传 `null`，也可以省略 `ids`：

```json
{"ids": null}
```

成功响应为二进制 `.xlsx` 文件：

```http
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="export_details_20260721_153000.xlsx"; filename*=UTF-8''...
```

注意：

- `ids: []` 会返回 HTTP 422，避免把“没有勾选”误操作成“导出全部”。
- `ids` 使用对应查询接口返回的 `id`，不使用报关单号、发票号等业务编号。
- 当前“导出全部”指数据库内该资源的全部有效记录，不受列表页面当前分页和筛选条件限制。
- 接口直接返回文件，不创建后台任务；ERP 应按文件流下载，不能按通用 JSON 响应解析。

---

## 6. Java 对接要点

- 文件任务用 `multipart/form-data`，汇总任务用 JSON。
- `X-ERP-User-Id` 传 ERP 用户唯一 ID；`X-ERP-User-Name` 传 UTF-8 URL 编码后的姓名快照，例如 Java 使用 `URLEncoder.encode(name, StandardCharsets.UTF_8)`。退税生成和冲销必须由 ERP 提供。
- `Idempotency-Key` 在同一次业务操作的网络重试中保持不变；用户主动再次生成时必须换新键。
- 金额字段用 `BigDecimal` 接收（接口返回字符串）。
- 日期时间用 `LocalDate` / `LocalDateTime`。
- `202` 仅表示任务接收成功，不等于业务完成。
- 轮询间隔 1~2 秒，进入 SUCCESS / PARTIAL / FAILED 后停止。
- FAILED 后先读 `error_message`，文件问题修正后重新创建任务。
- Excel 导出接口返回二进制文件流；Java 可使用 `ResponseEntity<byte[]>` 或流式转发给浏览器。

---

## 7. 推荐调用顺序

1. `POST /tasks` (CUSTOMS_MATERIAL_IMPORT) → 轮询至完成
2. `POST /tasks` (CUSTOMS_DECLARATION_IMPORT) → 轮询至完成
3. `POST /tasks` (PURCHASE_INVOICE_IMPORT) → 轮询至完成
4. `POST /tasks` (FOREX_IMPORT) → 轮询至完成
5. 通过查询接口验证入库数据
6. `POST /tasks` (REFUND_PACKAGE_GENERATE) → 轮询至完成 → 读取 `generation_id` 和输出目录
7. 需要撤销时 `POST /tasks` (REFUND_PACKAGE_REVERSE) → 轮询至完成

## 8. 数据库升级

已有数据库在启用本版本前执行：

```sql
SOURCE sql/20260716_task_reliability.sql;
SOURCE sql/20260721_refund_inventory_allocation.sql;
```

两个增量脚本通过 `information_schema` 判断字段和索引是否存在，兼容不支持 `ADD COLUMN IF NOT EXISTS` 的 MySQL，并允许安全重复执行。
`20260721_refund_inventory_allocation.sql` 还会把已有 `export_detail` 报关单号统一转换为“18位基础编号 + 3位商品项号”的21位格式。

新环境直接执行 `sql/init_database.sql`。数据库迁移必须先完成，再启动包含本版本代码的 Python 服务。
