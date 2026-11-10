# eBay 价格分析 BI — 设计契约

店铺分析目录下新增「价格分析」页面，把 eBay 在售刊登的售价与库存、谷仓海外仓库存放在
一个 BI 看板里对比。本文是三端并行开工的契约：表结构、接口、响应结构一旦改动，改这里。

UI 布局参考 `D:/JMH/项目/个人简历网址/erp-bi/index.html`（只参考布局，不照搬配色与假数据）。

## 1. 数据源与实测结论

| 用途 | 来源 | 字段 | 现状 |
| --- | --- | --- | --- |
| eBay 售价 | `ods_ebay_store_listing_latest` | `current_price` + `currency` | 原币十进制文本，不丢精度 |
| eBay 库存 | 同上 | `quantity` / `quantity_available` / `quantity_sold` | 接口原值，缺失不补零 |
| 店铺、站点 | 同上 | `seller_account` / `site` | site 由 ViewItemURL 域名识别，取值 DE/UK/US/FR |
| 谷仓海外仓可售 | `ods_goodcang_product_inventory_latest`（谷仓 `get_product_inventory`） | `sellable` | **每周快照**，非实时（2026-11-10 起，原为领星转述） |
| 海外在途 | 同上 | `onway`（不取 `total_onway`） | |
| 海外待出库 | 同上 | `reserved`（出库单已预占） | |
| 成都中转仓 | `ods_lingxing_inventory_detail_weekly` | `product_valid_num`，wid 18674/18675/18676 | 领星周快照，**不变** |
| 成都待出库 | 同上 | `product_lock_num` | 与海外 `reserved` 相加得 `pending_outbound` |
| 近 7/30 日销量 | `dwd_ebay_sku_analysis_order` | `purchase_quantity`，按 `payment_time` | 数字酋长订单，手动上传 |
| 采购成本 | `ods_ebay_sku_analysis_order_raw` | `purchase_cost_cny` | 真实成本，**不用售价 45% 估算** |
| 汇率 | `dim_lingxing_currency_month` | `my_rate` | 月度，按 `stat_month` 取 |

站点映射（listing 的 site → 库存的 site）：`DE→德国`、`UK→英国`、`US→美国`。
`FR` 只有 1 条且关联不上，归入「未匹配」，不单独建站点。

谷仓仓库 → 站点：`DE→德国`、`UK→英国`、`USEA`（新泽西）+ `USWE`（加州）→ `美国`（两仓合计）。
与领星 `warehouse.t_warehouse_code` / `goodcang_warehouse.wid` 的登记一致
（DE↔18699、USEA↔18700、USWE↔18701、UK↔18702）。`CZ`（捷克）没有 wid，**暂不纳入**，
等到货并定好站点归属再加；ODS 里原样保留。

### 实测关联命中率（2026-11-10 初版，领星口径，按站点 + 完整 SKU）

> 这张表是用 9 月那批 listing 算的，已过时，仅留档。换源依据见下面「换成谷仓」一节。

| 站点 | listing | 命中 | 命中率 |
| --- | --- | --- | --- |
| DE | 7333 | 6971 | 95.1% |
| UK | 5620 | 5456 | 97.1% |
| US | 5059 | 4139 | 81.8% |
| FR | 1 | 0 | 0% |

两边 SKU 同为 `品牌-中间码-尾号`（`TYT-90245-0772`），格式一致，**用完整 SKU 关联**。
降级到「品牌-中间码」只提升到 97.7% / 98.6% / 85.5%，不值得损失精度。
中间码只作为看板的分组与下钻维度。

### 换成谷仓（2026-11-10 用户决定）

调研见 `outputs/交接/谷仓库存接口-对数调研-回报.md`（不进仓库），用同一批 11-10 listing 对比：

| 站点 | 领星（站点 + 完整 SKU） | 谷仓（站点 + 去掉第一段） |
| --- | --- | --- |
| DE | 93.6% | 96.6% |
| UK | 96.2% | 98.6% |
| US | 87.4% | 90.0% |

- **可售口径相同**：同一天（09-16）领星 `product_valid_num` 与它自己记录的谷仓原数
  `third_inventory.qty_sellable` 99.1%–99.8% 相等，领星只是转述谷仓。换源不改变含义。
- **待出库、在途是口径不同**：领星 `product_lock_num` 几乎全为 0，谷仓 `reserved` 才是出库单预占数；
  领星 `product_onway` 比谷仓 `onway` 大（DE 10636 对 7145），多算了领星侧已建单、谷仓未登记的货。
- **关联键改为「站点 + 去掉 SKU 第一段后其余完整比对」**：谷仓 SKU 一律是 `JMH-…`，
  eBay / 领星是 `品牌-…`，去掉第一段后同一套编码。**不能只取中间码-尾号两段**——谷仓有 757 个
  两段 SKU、2468 个四段以上 SKU，取两段会错配。两边必须用同一个函数取 key。
- US 剩余未命中主要是 listing 侧写法（`-SY` 后缀 239 条、2PC 组合装 56 条、`-AMZUS1` 26 条），
  谷仓和领星都匹配不上，与换源无关。

US 偏低需在页面上可见：未匹配到库存的 listing 不许静默丢弃，计入「未匹配」并可筛选。
这条是硬要求 —— 静默丢弃会让库存缺口和超卖判断失真。

### 已知阻塞（不在本次开发范围，但影响上线效果）

- `ods_ebay_store_listing_latest` 最近拉取 **2026-09-23**，已停约 7 周
- `ods_lingxing_inventory_detail_weekly` 最新快照 **2026-09-16**，已停约 8 周

看板代码不依赖数据新鲜度，可以先开发。但上线时若两源仍是 9 月数据，看板展示的是 9 月快照。

## 2. 同步策略

**2026-11-10 用户决定：eBay 与谷仓都改为每周一次，绑在同一个任务里依次执行。**
任务 `pythonEbayStoreListingSyncTask.runWeekly()`，cron `0 30 4 ? * MON`（每周一 04:30）：
拉 eBay listing → 拉谷仓库存（`goodcang_product_inventory_sync`）→ 刷价格分析 DWS。

- listing 失败：整个任务失败，不刷表。
- 谷仓失败：单独告警，不推翻 listing，**仍刷表**（用上一份谷仓快照），摘要写明「本次谷仓未更新」。
- 刷表 409：等待后重试一次，仍失败只告警。
- 新鲜度告警阈值默认 8 天（每周 + 1 天余量）。
- 谷仓同步单独用锁 `goodcang:product-inventory:replace`，并且**单事务整表替换**；
  listing 同步按账号分多事务替换，所以刷表必须与它共用 `ebay:store-listing:replace`。

eBay 复用现有 `backend/services/ebay_store_listing_sync_service.py` 的全量逻辑，**不改该文件**。
（初版曾定为日级，后改为每周。）

规模实测：37 个账号 / 18013 条 listing，每页 100 条 → 一轮约 201 次 ActiveList + 37 次身份
接口 ≈ **240 次调用**。eBay Trading API 默认 5000 calls/day，每周一次远在额度内。

谷仓全量约 8246 行、每页 200、42 页，实测约 50 秒，未遇限流。

## 3. 表设计

新建 `dws_ebay_price_analysis`（`date-project` 库），日级同步后整表事务替换，不留历史批次。

```
stat_date              DATE         快照日期（= listing 的 pulled_at 日期）
seller_account         VARCHAR(128) 店铺
site                   VARCHAR(16)  DE/UK/US/FR
site_name              VARCHAR(16)  德国/英国/美国（未映射为空）
item_id                VARCHAR(64)
sku                    VARCHAR(255) 完整 SKU，TRIM 后
brand_code             VARCHAR(64)  SKU 第 1 段
mid_code               VARCHAR(128) SKU 前 2 段（品牌-中间码）
title                  TEXT
image_url              TEXT
view_item_url          TEXT
currency               VARCHAR(16)
current_price          DECIMAL(20,6) 原币售价
price_usd              DECIMAL(20,6) 折算 USD；汇率缺失为 NULL，不补 0
ebay_quantity          BIGINT
ebay_quantity_available BIGINT
ebay_quantity_sold     BIGINT
watch_count            BIGINT
overseas_sellable      BIGINT       谷仓海外仓可售
overseas_in_transit    BIGINT       海外在途
chengdu_sellable       BIGINT       成都中转仓可售
pending_outbound       BIGINT       待出库（锁定）
inventory_matched      TINYINT(1)   是否关联到库存
sales_qty_7d           BIGINT
sales_qty_30d          BIGINT
cover_days             DECIMAL(10,2) 覆盖天数；日均销量为 0 时 NULL，不写 0 或极大值
stock_gap              BIGINT       overseas_sellable − ebay_quantity_available
purchase_cost_cny      DECIMAL(20,6) 真实采购成本，缺失 NULL
status                 VARCHAR(16)  见下
sync_batch_id          VARCHAR(64)
refreshed_at           DATETIME
```

索引：`uk(seller_account,item_id)`、`idx(site,sku)`、`idx(mid_code)`、`idx(status)`。

### 状态判定（自上而下，命中即止）

| 状态 | 条件 |
| --- | --- |
| 未匹配 | `inventory_matched = 0` |
| 超卖风险 | `ebay_quantity_available > overseas_sellable + chengdu_sellable` |
| 断货 | `overseas_sellable = 0 且 ebay_quantity_available > 0` |
| 待补货 | `cover_days IS NOT NULL 且 cover_days < 15` |
| 滞销 | `sales_qty_30d = 0 且 overseas_sellable > 0` |
| 健康 | 其余 |

状态只在这张表里算一次，图表和明细都读它 —— 保证「图表 → 明细」口径一致。
前端不许自己再推导状态。

## 4. 接口契约

Python FastAPI 提供，Java 用 `PythonHttpSupport` 转发（与绩效排名、补货V2 一致）。

### `GET /api/v1/ebay-price-analysis/overview`

查询参数：`stat_date`、`sites`（逗号分隔）、`accounts`、`status`、`keyword`、`dimension`（`sku`|`mid`）

```json
{
  "stat_date": "2026-09-23",
  "refreshed_at": "2026-09-23 10:15:11",
  "kpis": [
    {"key": "listing_count", "label": "在售刊登", "value": 18013, "unit": "条"},
    {"key": "sku_count", "label": "在售SKU", "value": 9821, "unit": "个"},
    {"key": "ebay_available", "label": "eBay可售", "value": 52140, "unit": "件"},
    {"key": "overseas_sellable", "label": "谷仓可售", "value": 38920, "unit": "件"},
    {"key": "stock_gap", "label": "库存缺口", "value": -13220, "unit": "件"},
    {"key": "oversell_count", "label": "超卖风险", "value": 412, "unit": "条"},
    {"key": "unmatched_count", "label": "未匹配", "value": 1447, "unit": "条"},
    {"key": "avg_price_usd", "label": "均价", "value": 42.18, "unit": "USD"}
  ],
  "store_compare": [
    {"seller_account": "aplus-shop", "site": "DE", "ebay_available": 2140,
     "overseas_sellable": 1820, "listing_count": 981}
  ],
  "scatter": [
    {"sku": "TYT-90245-0772", "mid_code": "TYT-90245", "price_usd": 58.2,
     "overseas_sellable": 120, "ebay_available": 36, "status": "健康"}
  ],
  "scatter_median": {"price_usd": 38.5, "overseas_sellable": 42},
  "stock_gap_top": [
    {"sku": "BMW-30136-0128", "mid_code": "BMW-30136", "stock_gap": 860,
     "overseas_sellable": 900, "ebay_available": 40}
  ],
  "risks": [
    {"key": "oversell", "label": "超卖风险", "count": 412, "impact": 1,
     "hint": "eBay 可售超过谷仓+成都可用", "filter": {"status": "超卖风险"}}
  ]
}
```

`scatter` 按 `dimension` 聚合：`sku` 时一个点一个完整 SKU（跨店合计），`mid` 时按品牌-中间码。
点数超过 2000 时后端做抽样，并在响应里给 `scatter_sampled: true`，前端提示「已抽样」。

### `GET /api/v1/ebay-price-analysis/detail`

参数：上述筛选 + `mode`(`detail` 按店铺明细 / `summary` 按 SKU 汇总) + `page` + `page_size`
+ `sort_by` + `sort_order`

```json
{"total": 18013, "page": 1, "page_size": 50,
 "rows": [{"seller_account": "aplus-shop", "site_name": "德国", "sku": "TYT-90245-0772",
           "title": "...", "image_url": "...", "view_item_url": "...",
           "currency": "EUR", "current_price": 52.9, "price_usd": 58.2,
           "ebay_quantity_available": 36, "overseas_sellable": 120,
           "overseas_in_transit": 0, "chengdu_sellable": 40, "pending_outbound": 2,
           "sales_qty_7d": 3, "sales_qty_30d": 14, "cover_days": 280.0,
           "stock_gap": 84, "purchase_cost_cny": 186.4, "status": "健康"}]}
```

### `GET /api/v1/ebay-price-analysis/export`

同 `detail` 的筛选，返回 xlsx 流。导出列权限沿用补货V2 的做法（`sys_menu` 的 `exportColumn:*`）。

### 页面不提供触发刷表的接口

**2026-11-10 决定**：原先有一个 `POST /refresh`，页面上挂着「刷新数据源」按钮。
它只往请求表插一条 PENDING 记录就返回，既不拉 eBay 也不刷表，页面数据不变且无提示，
点了要等第二天 04:30 的定时任务才被消费 —— 名不副实，已连同请求表一并删除。

数据生产只走定时任务，页面只负责展示。三件事分三处，成本差三个数量级：

| 要做什么 | 在哪做 | 成本 |
| --- | --- | --- |
| 看最新数据 | 页面「刷新」按钮，重新调 overview / detail | 零 |
| 重算 DWS（读现有 listing 快照） | 定时任务执行 `ebay_price_analysis_refresh` | 秒级，零 API |
| 重拉 eBay + 重算 | 定时任务执行 `pythonEbayStoreListingSyncTask.runDaily()` | 分钟级，约 240 次 API |

后两件都是写库操作，按项目规矩不跑在用户请求线程里，也不做成页面上随手能点的按钮 ——
点几下就把当天 eBay API 额度耗掉了。

## 5. 前端布局

`operations/ebay/priceAnalysis/index.vue`，自上而下：

1. **页头** — 标题、快照日期与刷新时间、站点/店铺/状态筛选，以及两个按钮：
   「刷新」（重新调接口读表）和「导出明细」。两个按钮复用项目自有图标库的
   `jmh-refresh` / `jmh-export`，**图标不设颜色**，靠 `SvgIcon` 的 `fill: currentColor`
   继承按钮文字色（导出按钮是 `type="warning" plain`，全站导出按钮的约定），
   禁用时图标跟着变灰。不要照抄 `amzProfitReport` 里写死的 `color: #1296db` ——
   那边是纯图标按钮没有文字，必须显式给色。
2. **KPI 行** — 8 个指标卡，读 `kpis`，不在前端二次计算
3. **主图区（2 列）**
   - 店铺库存对比：eBay 可售 vs 谷仓可售，分组柱状图，点击柱体筛选下方明细
   - 价格 × 库存象限：散点，气泡大小 = eBay 可售，中位数虚线
4. **次图区（2 列）**
   - 库存缺口 Top 10：发散条形图，向右可补上架、向左超卖风险
   - 待处理事项：读 `risks`，点击跳到对应明细并带上筛选
5. **明细表** — 两种视图切换、搜索、状态下拉、店铺 chips、紧凑模式、分页
6. **口径说明** — 固定文案，写明周快照、汇率月度、覆盖天数算法、未匹配的处理

图表库沿用项目现有方案（与补货V2、库存明细一致），不引入新依赖。
配色沿用 ERP 现有 token，不照搬参考原型的配色。

## 6. 口径说明（页面底部固定文案）

- eBay 售价与库存为在售刊登快照，快照日期见页头
- eBay 售价与可售量为在售刊登**每周快照**（每周一更新）
- 海外仓库存为**谷仓区域仓接口每周快照**（DE / UK / 美东 USEA / 美西 USWE，美国两仓合计；捷克 CZ 暂不纳入），**不是实时库存**
- 成都中转仓库存仍为**领星周快照**
- 海外仓按「站点 + 去掉 SKU 第一段（品牌前缀，谷仓侧为 JMH）」匹配
- 覆盖天数 = 谷仓可售 ÷ 近 7 日日均销量；近 7 日无销量时不计算，显示「—」
- 售价按站点币种和领星月度汇率折算 USD，汇率缺失时不折算
- 采购成本取订单文件中的真实采购成本，未参与售价估算
- 未关联到库存的 listing 计入「未匹配」，不计入库存缺口与超卖判断

## 7. 任务拆分与文件边界

三个任务的文件**完全不重叠**，可并行。都只改代码不提交，由架构师统一核对后提交。

### 任务 A — Python 数据层与接口

```
新增 Date-Project/migrations/20261110_ebay_price_analysis.sql
新增 Date-Project/backend/repositories/ebay_price_analysis_repository.py
新增 Date-Project/backend/services/ebay_price_analysis_service.py
新增 Date-Project/backend/api/v1/ebay_price_analysis.py
新增 Date-Project/tests/test_ebay_price_analysis.py
```

建表 + 刷表（从两个 ODS 关联出 DWS）+ 状态判定 + 各图表的聚合查询 + FastAPI 路由。
Python 侧一并做完，避免 service 函数签名与路由层对不上。
状态判定必须有单元测试覆盖全部 6 种分支和边界（可售为 0、日均销量为 0、汇率缺失）。

### 任务 B — Java 转发与定时任务

```
新增 RuoYi-Vue-springboot3/.../controller/operations/EbayPriceAnalysisController.java
新增 RuoYi-Vue-springboot3/.../service/.../EbayPriceAnalysisPythonClient.java
新增 RuoYi-Vue-springboot3/.../task/PythonEbayStoreListingSyncTask.java
新增 RuoYi-Vue-springboot3/sql/20261110_ebay_price_analysis_menu.sql
新增 RuoYi-Vue-springboot3/.../test/.../EbayPriceAnalysisControllerTest.java
```

菜单挂在 `store-analysis` 目录下（`path='price-analysis'`、
`component='operations/ebay/priceAnalysis/index'`、`perms='operations:ebayPriceAnalysis:list'`、
`order_num=4`），含导出列权限，脚本幂等可重复执行。
定时任务只调用现有 `sync_ebay_store_listings`，**不修改该服务文件**。

### 任务 C — 前端

```
新增 RuoYi-Vue3-master/src/api/operations/ebayPriceAnalysis.js
新增 RuoYi-Vue3-master/src/views/operations/ebay/priceAnalysis/index.vue
新增 RuoYi-Vue3-master/tests/ebay-price-analysis.test.mjs
```

按第 5 节布局实现，所有数值直接用接口返回值，不在前端重算。

### 不在本次范围

- 两个数据源停摆的排查与恢复（另行处理）
- 组别（Ebay-1 组）筛选 —— 现有数据模型没有店铺到组的映射，先只按站点和店铺筛选
- 实时库存 —— 谷仓 API 已直连，但按用户决定每周拉一次，不做实时
