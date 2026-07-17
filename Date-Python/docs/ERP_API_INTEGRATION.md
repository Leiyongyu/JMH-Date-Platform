# JMH Python 数据服务 — ERP API 对接文档

版本：v1.1 | 基础地址：`http://<python-host>:5000/api/v1` | 框架：FastAPI

---

## 1. 接口设计

- 耗时写操作（上传、解析、匹配、入库、汇总生成）统一通过 `POST /tasks` 创建异步任务，返回 `task_id` 后轮询 `GET /tasks/{id}` 获取进度和结果。
- 已入库数据通过资源型接口分页查询。
- Java ERP 使用 `X-ERP-User` 请求头传递操作人。
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
| 6 | `GET /tasks/{id}` | — | — | 查询任务状态与结果 |
| 7 | `GET /tasks` | — | — | 分页查询任务历史 |

### 查询型（同步）

| # | 方法 | 说明 |
|---|------|------|
| 8 | `GET /customs-material-items` | 报关资料商品查询 |
| 9 | `GET /export-details` | 出口明细分页查询 |
| 10 | `GET /purchase-inventory` | 进货库存分页查询 |
| 11 | `GET /forex-receivables` | 外汇应收分页查询 |

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
X-ERP-User: admin
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
X-ERP-User: admin
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_type` | string | ✅ | `CUSTOMS_DECLARATION_IMPORT` |
| `file` | file(.pdf) | ✅ | PDF 标题须含"中华人民共和国海关出口货物报关单"，可传多个 |
| `declaration_month` | string | ❌ | 申报年月 `YYYYMM`，不填则从报关单推断 |
| `declaration_batch` | string | ❌ | 申报批次（1~3位数字），填了则生成关联号，不填仅生成序号 |
| `export_date` | string | ❌ | 统一出口日期 `YYYY-MM-DD`，覆盖 PDF 中各商品日期 |

**前置条件**: 对应合同的报关资料 Excel 须先导入。

**处理逻辑**: 解析 PDF → 提取报关单头 + 商品表 → 按合同号 + 标准化项号匹配报关资料 Excel → 自动生成序号（00000001 起）→ upsert 到 `export_detail`。

---

### 4.3 进货发票 PDF 导入

解析增值税专用发票 PDF，增量保存进货库存。

```http
POST /api/v1/tasks
Content-Type: multipart/form-data
X-ERP-User: admin
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_type` | string | ✅ | `PURCHASE_INVOICE_IMPORT` |
| `file` | file(.pdf) | ✅ | 电子发票 PDF |
| `declaration_month` | string | ❌ | 申报年月 `YYYYMM` |
| `declaration_batch` | string | ❌ | 申报批次，填了则生成关联号回写进货表 |

**处理逻辑**: 解析 PDF → 提取发票头 + 商品行 → 按发票号 + 项号 upsert → 每发票独立序号 → 有批次时自动生成关联号。

---

### 4.4 外汇回款 Excel 导入

解析外汇回款汇总表 Sheet1，增量保存应收、回款及分配。

```http
POST /api/v1/tasks
Content-Type: multipart/form-data
X-ERP-User: admin
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
X-ERP-User: admin

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
| `export_ids` | int[] | ❌ | `null` | 指定出口明细 ID，不传=全部 |

**输出目录结构**:
```
{output_parent_dir}/汇总/
├── 001/                          ← 按供货方退税金额降序编号
│   ├── 《外贸企业出口退税进货明细申报表》导入模板-{纳税号}-001.xlsx
│   ├── 《外贸企业出口退税出口明细申报表》导入模板-{纳税号}-001.xlsx
│   └── 出口业务收汇情况表_{纳税号}_001.xlsx
├── 002/ ...
├── 出口业务收汇情况表_汇总.xlsx      ← 所有供货方合并
└── 企业收汇情况表.xlsx              ← 企业级汇总
```

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

**返回字段**: `id`, `invoice_no`, `invoice_date`, `invoice_item_no`, `sku_normalized`, `product_name`, `unit`, `supplier_name`, `supplier_tax_no`, `purchased_quantity`, `remaining_quantity`, `unit_price`, `taxable_amount`, `tax_rate`, `tax_amount`, `inventory_status`, `declaration_month`, `declaration_batch`, `sequence_no`, `relation_no` 等。

---

### 5.6 外汇应收 `GET /forex-receivables`

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

## 6. Java 对接要点

- 文件任务用 `multipart/form-data`，汇总任务用 JSON。
- `X-ERP-User` 传递操作人 ID。
- 金额字段用 `BigDecimal` 接收（接口返回字符串）。
- 日期时间用 `LocalDate` / `LocalDateTime`。
- `202` 仅表示任务接收成功，不等于业务完成。
- 轮询间隔 1~2 秒，进入 SUCCESS / PARTIAL / FAILED 后停止。
- FAILED 后先读 `error_message`，文件问题修正后重新创建任务。

---

## 7. 推荐调用顺序

1. `POST /tasks` (CUSTOMS_MATERIAL_IMPORT) → 轮询至完成
2. `POST /tasks` (CUSTOMS_DECLARATION_IMPORT) → 轮询至完成
3. `POST /tasks` (PURCHASE_INVOICE_IMPORT) → 轮询至完成
4. `POST /tasks` (FOREX_IMPORT) → 轮询至完成
5. 通过查询接口验证入库数据
6. `POST /tasks` (REFUND_PACKAGE_GENERATE) → 轮询至完成 → 读取输出目录
