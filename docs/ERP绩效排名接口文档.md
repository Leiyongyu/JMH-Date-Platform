# ERP 绩效排名 REST 接口文档

## 1. 文档范围

本文档用于 ERP（RuoYi/Spring Boot）通过服务间 HTTP 调用 Python 绩效服务，完成月份选择、排名查询、eBay 利润表上传、AMZ/eBay 负责人表上传和指定月份排名刷新。

领星 OpenAPI 同步及 Python 内部定时任务不属于 ERP 对接接口。

接口版本：`v1`

## 2. 服务地址

开发环境：

```text
http://127.0.0.1:8010
```

如果 Java ERP 与 Python 服务部署在同一台服务器，建议 Java 后端始终通过 `127.0.0.1:8010` 调用。若部署在不同服务器，应使用内网地址或带鉴权的反向代理地址。

> `8.177.137.25` 当前用于转发 Python 到领星 OpenAPI 的出站请求，不应直接作为 ERP 调用 Python 服务的地址，除非该服务器另外配置了指向本接口的反向代理。

公共约定：

| 项目 | 约定 |
|---|---|
| 协议 | HTTP（仅本机/内网）或 HTTPS（跨服务器） |
| 编码 | UTF-8 |
| 响应格式 | `application/json` |
| 金额币种 | CNY |
| 月份格式 | `YYYY-MM` |
| 时间区间 | 对应自然月 |

## 3. 请求追踪

ERP 可以在请求头传入自己的请求编号：

```http
X-Request-ID: erp-performance-202606-001
```

Python 服务会：

- 在响应头原样返回 `X-Request-ID`；
- 在响应 JSON 的 `request_id` 中返回相同值；
- 未传时自动生成 UUID。

联调或生产排错时，双方日志应使用此编号关联。

## 4. ERP 接口总览与月份规则

### 4.1 接口总览

| 方法 | Path | ERP 用途 | 月份来源 |
|---|---|---|---|
| GET | `/api/v1/finance/performance-months` | 获取月份下拉框及各平台就绪状态 | 数据仓库 |
| GET | `/api/v1/finance/performance-rankings` | 按月份、平台查询排名 | Query 参数 `stat_month` |
| POST | `/api/v1/finance/ebay-profit-imports` | 上传 eBay 月度利润表 | Excel 文件名中的 `YYYYMM` |
| POST | `/api/v1/finance/performance-owner-rule-imports?platform=amazon` | 上传 AMZ 负责人表 | Excel 列名 `YYYYMM负责人` |
| POST | `/api/v1/finance/performance-owner-rule-imports?platform=ebay` | 上传 eBay 负责人表 | Excel 列名 `YYYYMM负责人` |
| GET | `/api/v1/finance/performance-owner-rule-summaries` | 查询指定月份负责人规则摘要 | Query 参数 `stat_month` |
| POST | `/api/v1/finance/performance-refreshes` | 重算指定月份排名 | JSON 字段 `stat_month` |

### 4.2 月份选择流程

ERP 页面推荐按以下顺序工作：

1. 页面加载时调用 `/performance-months` 获取可选月份；
2. 用户选择月份后，将 `stat_month=YYYY-MM` 传给 `/performance-rankings`；
3. 用户上传负责人表或 eBay 利润表时，默认 `rebuild=true`，上传成功后自动重算对应月份；
4. 上传使用 `rebuild=false` 时，ERP 再调用 `/performance-refreshes` 手工重算；
5. 最后重新调用 `/performance-months` 和 `/performance-rankings` 刷新页面。

三种月份格式不能混用：

| 使用位置 | 正确格式 | 示例 |
|---|---|---|
| REST Query/JSON | `YYYY-MM` | `2026-06` |
| 负责人 Excel 列名 | `YYYYMM负责人` | `202606负责人` |
| eBay 利润 Excel 文件名 | 文件名包含 `YYYYMM` | `ebay-202606-利润表.xlsx` |

## 5. 获取可选择月份

### 5.1 接口定义

```http
GET /api/v1/finance/performance-months?limit=12
```

### 5.2 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `limit` | integer | 否 | `12` | 返回最近月份数量；服务端限制为 1～60 |

月份来自 AMZ 利润明细、eBay 利润明细和综合排名表的月份并集，按月份倒序返回。

### 5.3 成功响应

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "stat_month": "2026-06",
      "amazon_ready": true,
      "ebay_ready": true,
      "combined_ready": true,
      "partial": false,
      "last_refreshed_at": "2026-07-30T10:30:00"
    }
  ],
  "request_id": "erp-months-001"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `stat_month` | string | 月份，ERP 下拉框的值 |
| `amazon_ready` | boolean | AMZ 排名是否已生成 |
| `ebay_ready` | boolean | eBay 排名是否已生成 |
| `combined_ready` | boolean | 综合排名是否已生成 |
| `partial` | boolean | 综合排名是否只有部分平台数据 |
| `last_refreshed_at` | string/null | 最近一次排名刷新时间 |

ERP 下拉框显示建议为：`2026-06（AMZ✓ / eBay✓ / 综合✓）`。

## 6. 查询绩效排名

### 6.1 接口定义

```http
GET /api/v1/finance/performance-rankings
```

### 6.2 Query 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `platform` | string | 否 | `combined` | `combined`（综合）、`amazon`、`ebay` |
| `stat_month` | string | 否 | 最新月份 | 格式 `YYYY-MM`，例如 `2026-06` |
| `principal_name` | string | 否 | - | 按负责人名称模糊查询，中文需进行 URL 编码 |
| `order_by` | string | 否 | `gross_profit` | `gross_profit` 或 `net_sales_amount` |
| `order` | string | 否 | `desc` | `desc` 或 `asc` |
| `page` | integer | 否 | `1` | 页码，建议传大于等于 1 的整数 |
| `page_size` | integer | 否 | `100` | 每页数量，范围 1～1000 |

说明：

- 不传 `stat_month` 时，查询所选平台已有排名数据中的最新月份；
- `combined` 是 AMZ 与 eBay 按负责人汇总后的综合排名；
- 排序金额相同时，结果使用数据表主键保证稳定顺序；
- `principal_name` 为空时查询全部负责人。

同一个接口通过 `platform` 选择对应月份的平台数据：

```http
# 2026-06 综合排名
GET /api/v1/finance/performance-rankings?platform=combined&stat_month=2026-06

# 2026-06 AMZ 排名
GET /api/v1/finance/performance-rankings?platform=amazon&stat_month=2026-06

# 2026-06 eBay 排名
GET /api/v1/finance/performance-rankings?platform=ebay&stat_month=2026-06
```

### 6.3 请求示例

```http
GET /api/v1/finance/performance-rankings?platform=combined&stat_month=2026-06&order_by=gross_profit&order=desc&page=1&page_size=100 HTTP/1.1
Host: 127.0.0.1:8010
Accept: application/json
X-Request-ID: erp-performance-202606-001
```

cURL：

```bash
curl "http://127.0.0.1:8010/api/v1/finance/performance-rankings?platform=combined&stat_month=2026-06&order_by=gross_profit&order=desc&page=1&page_size=100" \
  -H "Accept: application/json" \
  -H "X-Request-ID: erp-performance-202606-001"
```

### 6.4 成功响应

HTTP 状态码：`200 OK`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "platform": "combined",
    "stat_month": "2026-06",
    "currency": "CNY",
    "partial": false,
    "items": [
      {
        "principalNames": "张三",
        "grossProfit": "123456.780000",
        "netSalesAmount": "456789.120000"
      },
      {
        "principalNames": "李四",
        "grossProfit": "102400.000000",
        "netSalesAmount": "398000.000000"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 100,
      "total": 2
    }
  },
  "request_id": "erp-performance-202606-001"
}
```

### 6.5 响应字段

统一响应：

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | integer | 成功固定为 `0` |
| `message` | string | 成功为 `success` |
| `data` | object | 查询结果 |
| `request_id` | string | 请求追踪编号 |

`data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `platform` | string | 本次查询的平台 |
| `stat_month` | string/null | 实际返回的月份；无任何排名月份时为 `null` |
| `currency` | string | 固定为 `CNY` |
| `partial` | boolean | `true` 表示综合数据中至少一个平台当月未就绪 |
| `items` | array | 负责人绩效数据 |
| `pagination` | object | 分页信息 |

`items` 中每条记录只包含 ERP 所需的三个业务字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `principalNames` | string/null | 负责人；历史 ERP 字段名为复数，但实际是单个负责人 |
| `grossProfit` | string | 毛利润，十进制金额字符串 |
| `netSalesAmount` | string | 净销售额，十进制金额字符串 |

金额使用字符串返回，ERP 应使用 `BigDecimal` 解析，不能使用 `double`。

`pagination`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `page` | integer | 当前页 |
| `page_size` | integer | 每页数量 |
| `total` | integer | 符合条件的总记录数 |

### 6.6 无数据响应

查询月份合法但尚无排名数据时仍返回 `200 OK`，不是错误：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "platform": "combined",
    "stat_month": "2026-05",
    "currency": "CNY",
    "partial": false,
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 100,
      "total": 0
    }
  },
  "request_id": "erp-performance-202605-001"
}
```

ERP 页面应显示“该月份暂无绩效数据”，不应弹出系统异常。

## 7. 上传 eBay 月度利润表

### 7.1 接口定义

```http
POST /api/v1/finance/ebay-profit-imports
Content-Type: multipart/form-data
```

### 7.2 Query 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `rebuild` | boolean | 否 | `true` | 导入成功后是否自动重算 eBay 和综合排名 |
| `operator` | string | 否 | - | ERP 当前登录用户名称或账号，用于审计 |

Multipart 表单字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `file` | file | 是 | eBay 月度利润 Excel，推荐 `.xlsx` |

请求头建议：

```http
X-Request-ID: erp-ebay-profit-202606-001
Idempotency-Key: ebay-profit-202606-v1
```

### 7.3 月份识别及 Excel 约束

月份不通过 Query 参数传递，而是从原始文件名识别。文件名必须包含合法的六位年月：

```text
ebay-202606-利润表.xlsx
```

Excel 必须包含 `Sheet1`（大小写不敏感），且表头必须包含：

| 必需列 | 用途 |
|---|---|
| `SKU` | 识别品牌码并关联负责人 |
| `图片` | 商品图片 |
| `是否多属性` | 多属性标识 |
| `利润` | 毛利润 |
| `商品销售额` | 商品销售额 |
| `应收运费` | 应收运费 |
| `退款金额` | 退款金额 |

计算规则：

```text
销售额 = 商品销售额 + 应收运费
净销售额 = 销售额 - 退款金额
```

品牌码默认取 SKU 第一个 `-` 前的片段；如果 SKU 以 `数字PC-` 开头，则取第二段作为品牌码。

同月份重新上传会先清空该月份原 eBay ODS/DWD 利润数据，再以本次文件整月覆盖。该过程在数据库事务内完成。

### 7.4 请求示例

```bash
curl -X POST "http://127.0.0.1:8010/api/v1/finance/ebay-profit-imports?rebuild=true&operator=admin" \
  -H "X-Request-ID: erp-ebay-profit-202606-001" \
  -H "Idempotency-Key: ebay-profit-202606-v1" \
  -F "file=@ebay-202606-利润表.xlsx"
```

### 7.5 成功响应

HTTP 状态码：`201 Created`

```json
{
  "code": 0,
  "message": "ebay profit imported",
  "data": {
    "batch_id": "b4cc59de-5fa9-4bc2-b231-f631b5dd3910",
    "stat_month": "2026-06",
    "inserted_rows": 977,
    "totals": {
      "gross_profit": "108600.000000",
      "sales_amount": "680000.000000",
      "refund_amount": "22000.000000",
      "net_sales_amount": "658000.000000"
    },
    "refresh": {
      "refresh_id": "ab6b03de-d48c-49c7-9b97-94246bcc451e",
      "stat_month": "2026-06",
      "platform": "ebay",
      "currency": "CNY",
      "partial": false,
      "ebay_profit_rows": 977,
      "ebay_ranking_rows": 4,
      "combined_ranking_rows": 17,
      "status": "completed"
    }
  },
  "request_id": "erp-ebay-profit-202606-001"
}
```

`rebuild=false` 时 `data.refresh` 为 `null`，ERP 应随后调用指定月份刷新接口。

## 8. 上传 AMZ 负责人表

### 8.1 接口定义

```http
POST /api/v1/finance/performance-owner-rule-imports?platform=amazon
Content-Type: multipart/form-data
```

### 8.2 参数

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---:|---|---|
| `platform` | Query | string | 是 | - | AMZ 固定传 `amazon` |
| `rebuild` | Query | boolean | 否 | `true` | 导入后自动重算排名 |
| `stat_month` | Query | string | 否 | Excel 中全部月份 | 仅限制导入后自动重算的月份，格式 `YYYY-MM` |
| `operator` | Query | string | 否 | - | ERP 操作人 |
| `file` | Multipart | file | 是 | - | AMZ 负责人 Excel |

> `stat_month` 不会过滤 Excel 中导入的规则。Excel 内所有合法月份列都会写入仓库；该参数只控制本次自动重算哪个月份。

### 8.3 Excel 格式

工作簿必须同时包含以下四个 Sheet：

| Sheet | 匹配列 | 匹配逻辑 |
|---|---|---|
| `EU-品牌` | `品牌` | EU 普通 SKU 按品牌匹配 |
| `EU-OTH` | `中间码-OTH` | EU 的 `OTH-` SKU 按中间码匹配 |
| `US1` | `店铺名` | US1 按店铺名匹配 |
| `US2` | `店铺名` | US2 按店铺名匹配 |

每个 Sheet 至少包含一个月份负责人列，列名必须严格符合：

```text
202606负责人
202607负责人
```

示例：

| 品牌 | 202606负责人 | 202607负责人 |
|---|---|---|
| ABC | 张三 | 李四 |
| XYZ | 王五 | 王五 |

同平台、同月份、同分组、同规则类型、同匹配键不能在文件中重复，否则整个上传返回 `400`。

### 8.4 请求示例

只自动重算 2026-06，但仍导入 Excel 中全部月份列：

```bash
curl -X POST "http://127.0.0.1:8010/api/v1/finance/performance-owner-rule-imports?platform=amazon&rebuild=true&stat_month=2026-06&operator=admin" \
  -H "X-Request-ID: erp-amz-owner-202606-001" \
  -H "Idempotency-Key: amz-owner-202606-v1" \
  -F "file=@AMZ负责人.xlsx"
```

### 8.5 成功响应

HTTP 状态码：`201 Created`

```json
{
  "code": 0,
  "message": "owner rules imported",
  "data": {
    "batch_id": "74b11c34-f7d7-4da6-92e7-c8b21458385b",
    "platform": "amazon",
    "imported_rows": 86,
    "months": ["2026-06", "2026-07"],
    "month_count": 2,
    "refreshes": [
      {
        "stat_month": "2026-06",
        "platform": "amazon",
        "amz_ranking_rows": 13,
        "combined_ranking_rows": 17,
        "status": "completed"
      }
    ]
  },
  "request_id": "erp-amz-owner-202606-001"
}
```

## 9. 上传 eBay 负责人表

### 9.1 接口定义

```http
POST /api/v1/finance/performance-owner-rule-imports?platform=ebay
Content-Type: multipart/form-data
```

参数与 AMZ 负责人上传一致，但 `platform` 固定传 `ebay`。

### 9.2 Excel 格式

工作簿必须包含 `Sheet1`，并包含：

- 一列 `品牌`；
- 至少一列符合 `YYYYMM负责人` 格式的月份列。

示例：

| 品牌 | 202606负责人 | 202607负责人 |
|---|---|---|
| ABC | 张三 | 李四 |
| XYZ | 王五 | 王五 |

负责人规则按 eBay 利润表 SKU 解析出的品牌码匹配。品牌值导入时统一转换为大写。

### 9.3 请求示例

```bash
curl -X POST "http://127.0.0.1:8010/api/v1/finance/performance-owner-rule-imports?platform=ebay&rebuild=true&stat_month=2026-06&operator=admin" \
  -H "X-Request-ID: erp-ebay-owner-202606-001" \
  -H "Idempotency-Key: ebay-owner-202606-v1" \
  -F "file=@ebay对应负责人.xlsx"
```

### 9.4 成功响应

```json
{
  "code": 0,
  "message": "owner rules imported",
  "data": {
    "batch_id": "4d45884b-0476-4c53-9f77-6e33f51d542e",
    "platform": "ebay",
    "imported_rows": 42,
    "months": ["2026-06"],
    "month_count": 1,
    "refreshes": [
      {
        "stat_month": "2026-06",
        "platform": "ebay",
        "ebay_ranking_rows": 4,
        "combined_ranking_rows": 17,
        "status": "completed"
      }
    ]
  },
  "request_id": "erp-ebay-owner-202606-001"
}
```

负责人规则采用更新写入：相同平台、月份和匹配键再次上传时更新负责人；文件中不存在的旧规则不会自动删除。

## 10. 查询指定月份负责人规则摘要

### 10.1 接口定义

```http
GET /api/v1/finance/performance-owner-rule-summaries?platform=amazon&stat_month=2026-06
```

### 10.2 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `platform` | string | 是 | `amazon` 或 `ebay` |
| `stat_month` | string | 是 | `YYYY-MM` |

### 10.3 成功响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "platform": "amazon",
    "stat_month": "2026-06",
    "items": [
      {
        "group_code": "EU",
        "rule_type": "BRAND",
        "rule_count": 20,
        "last_updated_at": "2026-07-30T10:30:00"
      },
      {
        "group_code": "US1",
        "rule_type": "STORE",
        "rule_count": 12,
        "last_updated_at": "2026-07-30T10:30:00"
      }
    ]
  },
  "request_id": "erp-owner-summary-202606-001"
}
```

该接口用于上传前后检查指定月份规则是否存在，不返回负责人明细。

## 11. 刷新指定月份排名

### 11.1 接口定义

```http
POST /api/v1/finance/performance-refreshes
Content-Type: application/json
```

请求体：

```json
{
  "stat_month": "2026-06",
  "platform": "combined",
  "require_all_platforms": false
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `stat_month` | string | 是 | - | 要重算的月份，格式 `YYYY-MM` |
| `platform` | string | 否 | `combined` | `combined`、`amazon` 或 `ebay` |
| `require_all_platforms` | boolean | 否 | `false` | 为 `true` 时，AMZ/eBay 任一源数据缺失返回 `409` |

刷新逻辑：

- `amazon`：重算 AMZ 排名，并更新综合排名；
- `ebay`：重算 eBay 排名，并更新综合排名；
- `combined`：重算已有源数据的平台，再更新综合排名；
- 源数据不完整且允许继续时，`partial=true`。

### 11.2 成功响应

HTTP 状态码：`201 Created`

```json
{
  "code": 0,
  "message": "performance ranking refreshed",
  "data": {
    "refresh_id": "49c75058-b431-454a-9634-f7120d2232e5",
    "stat_month": "2026-06",
    "platform": "combined",
    "currency": "CNY",
    "partial": false,
    "amz_profit_rows": 13533,
    "ebay_profit_rows": 977,
    "source_rows": 10593,
    "matched_rows": 10213,
    "unmatched_rows": 380,
    "missing_shop_rows": 0,
    "amz_ranking_rows": 13,
    "ebay_ranking_rows": 4,
    "combined_ranking_rows": 17,
    "status": "completed"
  },
  "request_id": "erp-refresh-202606-001"
}
```

## 12. 错误响应

### 12.1 参数校验失败

HTTP 状态码：`422 Unprocessable Entity`

例如传入 `stat_month=2026-13`：

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["query", "stat_month"],
      "msg": "String should match pattern '^20\\d{2}-(0[1-9]|1[0-2])$'",
      "input": "2026-13"
    }
  ]
}
```

### 12.2 上传文件错误

HTTP 状态码：`400 Bad Request`

```json
{
  "detail": "eBay利润文件缺少列: 退款金额"
}
```

常见原因：

- eBay 利润文件名没有合法 `YYYYMM`；
- 缺少 `Sheet1` 或必需列；
- AMZ 负责人文件缺少四个固定 Sheet；
- 负责人文件没有 `YYYYMM负责人` 列；
- 同一个匹配键在同月份重复。

### 12.3 数据未就绪

HTTP 状态码：`409 Conflict`

当刷新请求设置 `require_all_platforms=true`，但指定月份 AMZ 或 eBay 数据缺失时返回：

```json
{
  "detail": "指定月份 AMZ/eBay 数据未全部就绪"
}
```

### 12.4 服务内部错误

HTTP 状态码：`500 Internal Server Error`

可能原因包括数据库连接失败、排名表不存在或 SQL 执行异常。ERP 应记录 HTTP 状态码、响应内容和 `X-Request-ID`，页面显示“绩效服务暂不可用”。

## 13. ERP 接入映射

ERP 页面已有字段可以直接映射：

| Python 返回字段 | ERP 字段 | Java 类型 |
|---|---|---|
| `principalNames` | `principalNames` | `String` |
| `grossProfit` | `grossProfit` | `BigDecimal` |
| `netSalesAmount` | `netSalesAmount` | `BigDecimal` |
| `data.pagination.total` | 列表总数 | `Long` |
| `data.items` | `rows` | `List<PerformanceRankingDto>` |

若 ERP 前端继续使用 RuoYi 列表响应格式，Java 后端适配层应转换为：

```json
{
  "code": 200,
  "msg": "查询成功",
  "rows": [
    {
      "principalNames": "张三",
      "grossProfit": "123456.780000",
      "netSalesAmount": "456789.120000"
    }
  ],
  "total": 1
}
```

建议由 Java 后端调用 Python 服务并完成响应转换，不建议浏览器直接跨域调用 Python 服务。

## 14. Java 配置建议

ERP 配置文件使用独立配置项，不要把 Python 地址写死在代码中：

```yaml
jmh:
  performance-service:
    base-url: http://127.0.0.1:8010
    connect-timeout: 3s
    read-timeout: 15s
```

调用时应满足：

- 连接超时建议 3 秒，读取超时建议 15 秒；
- GET 查询是幂等请求，连接失败或 `502/503/504` 时最多重试 2 次；
- `4xx` 参数错误不重试；
- 日志记录 `platform`、`stat_month`、HTTP 状态码和 `X-Request-ID`；
- `partial=true` 时 ERP 可展示“部分平台数据未就绪”提示。

## 15. 网络与安全

当前 Python 接口自身未实现登录态或 API Key 校验，因此只能通过以下方式之一部署：

1. Java ERP 与 Python 同机，通过 `127.0.0.1:8010` 调用；
2. 不同服务器之间仅开放内网访问，并使用防火墙限制来源 IP；
3. 通过 Nginx/网关暴露 HTTPS 地址，并在网关增加服务鉴权。

不得直接将 `8010` 端口无鉴权暴露到公网。

## 16. ERP 页面调用顺序

页面初始化：

```text
GET performance-months
  → 用户选择月份
  → GET performance-rankings?stat_month=所选月份
```

上传 eBay 利润：

```text
POST ebay-profit-imports?rebuild=true
  → 读取响应中的 stat_month
  → GET performance-months
  → GET performance-rankings?platform=combined&stat_month=响应月份
```

上传 AMZ/eBay 负责人：

```text
POST performance-owner-rule-imports?platform=amazon或ebay&rebuild=true&stat_month=所选月份
  → GET performance-owner-rule-summaries?platform=对应平台&stat_month=所选月份
  → GET performance-rankings?platform=combined&stat_month=所选月份
```

建议 ERP 的文件上传超时设置为 120 秒，因为 `rebuild=true` 会在上传后同步执行排名重算。

## 17. 联调检查清单

- Python 服务已启动并监听 `8010`；
- ERP 服务器可以访问配置的 Python Base URL；
- 查询 `2026-06` 能返回 `data.items`；
- 月份下拉来自 `/performance-months`，不在 ERP 中写死；
- eBay 利润文件名包含正确的 `YYYYMM`；
- AMZ 负责人文件包含四个固定 Sheet；
- 两类负责人文件都包含 `YYYYMM负责人` 列；
- 上传接口使用 `multipart/form-data`，文件字段名固定为 `file`；
- 上传成功后使用响应月份重新查询排名；
- ERP 使用 `BigDecimal` 解析两个金额字段；
- ERP 将 `data.items` 转换为 `rows`，将 `data.pagination.total` 转换为 `total`；
- 无数据时页面显示空状态；
- `partial=true` 时页面提示部分平台数据缺失；
- 双方日志可以通过 `X-Request-ID` 对应。
