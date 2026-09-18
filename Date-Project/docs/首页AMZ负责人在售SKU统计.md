# 首页 AMZ 负责人在售 SKU 统计

## 最新：独立Python原始源（2026-09-18）

首页AMZ改读 `date-project.ods_lingxing_amz_listing_latest`。新任务每周四10:00，完整保存58个一级字段及raw_json，全量校验成功后事务覆盖。原Java任务已恢复全部旧参数，服务原AMZ补货。最新部署步骤见 `../deploy/amz-listing-raw/部署说明.md`，以下历史验收数量不代表新源结果。

## 当月负责人补零（2026-09-18）

首页AMZ/eBay图表保留当月负责人规则中的人员，没有匹配到在售SKU也显示0，并计入负责人数量；同一人多条规则只显示一次。eBay仅从EBAY_BRAND规则读取人员。空负责人、“未分配”占位或“注销”状态不凭空添加零行，已有匹配结果不改写。零值按数量排序置于末尾，显示数字0但不画有色柱条。缺规则或最近同步未成功时仍返回异常状态，不补零掩盖问题。源数据正常但整个平台没有在售记录时，显示当月人员的零值列表。无需SQL，不写库，不触发同步。

## PC前缀排除（2026-09-18）

AMZ/eBay 首页统计均在负责人匹配及去重前排除首段为 `PC` 或任意数字加 `PC` 的SKU，例如 `2PC-`、`4PC-`、`12PC-`，忽略大小写和首尾空白。仅检查首段，不排除 `BMW-2PC-1` 这类中间包含PC的SKU。AMZ检查 `local_sku` 和 `seller_sku`，任一匹配即排除；eBay检查完整 `msku`。不再将这些商品跳过包装前缀后计入负责人。返回 `excluded_pc_rows` 记录被排除的源行数（不是去重后的SKU数）。仅作用于首页统计，不删除刊登数据，不修改绩效、补货和月度库存逻辑，无需SQL。

## eBay 扩展（2026-09-18）

首页同时展示 AMZ/eBay 两张图表，不设置切换按钮、不合并两个平台数量。桌面每行预留四张卡片（当前两张各占一格），小于1200px两列、小于640px一列。卡片高360px，横向柱条在卡片内部上下滚动，支持键盘聚焦滚动，各自独立刷新。完整统计说明移至底部悬浮提示。eBay 只读 `ebay_product_listing WHERE listing_status=1`；来源接口 `/basicOpen/multiplatform/ebay/list`。

先排除PC前缀MSKU，再按完整 `msku` 提取品牌前缀，复用 `parse_brand_code_from_sku` 及现有 `_ebay_assignment`，不传仓库SKU转换字典。对应 `EBAY_BRAND` 当月规则；首页统计已取消 CL→陈丽的固定归属，CL只查当月负责人表，无配置归“未分配”。FLL/LEJ→方黎力的原例外仍保留。不使用截短的 `sku`，不使用可能为空的 `local_sku`。此次仅改变首页统计，原绩效排名和月度库存的共享匹配逻辑不变。

按 `(负责人, 完整大写MSKU)` 去重，同店铺多个item_id及跨店铺同一MSKU都只计一次。不按中间码合并，不同后缀保留为不同MSKU。先过滤在售再匹配，不使用 `ebay_product_dedup`。仅缺MSKU的不计入并提示，店铺ID为空不影响计数。规则月份为中国时区当前月，不读取未来月份。AMZ的现行口径见下文。

2026-09-18 去重及归属调整：本地两个CL品牌MSKU各分布在6个店铺，12条在售刊登计为2个SKU。9月负责人表无CL配置，取消首页固定归属后这2个SKU计入“未分配”，不再显示为陈丽的数量。

新增 Java `GET /operations/ebay/owner-sku/summary`，复用权限 `operations:ebayReplenishmentV2:list`；Python `GET /api/v1/finance/ebay-owner-sku/summary` 沿用内部令牌保护。仅有 AMZ 权限不能访问 eBay 数据，反之亦然；无权限的平台图表不挂载、不发请求。两张图表的请求、加载及错误状态相互独立。

最近一次非SKIPPED的 `ebay_listing` 同步非SUCCESS时不展示可能不完整的统计。刷新统计不触发同步。现有eBay刊登任务采用按item_id增量upsert，未返回的旧记录不会自动删除；看板如实统计当前表内状态，不改动共享同步任务的口径。

不需要新增 SQL、表或任务；重启新版 Java/Python 并发布新版前端。新增 Python 测试 `tests/test_ebay_owner_sku.py`，Java 测试 `EbayOwnerSkuControllerTest`。

早期扩展验证时，eBay刊登同步日志562处于RUNNING（开始时间2026-09-18 11:23:51），正式统计接口正确返回SOURCE_NOT_READY；没有额外触发同步。当时按旧的店铺MSKU口径预览合计16,671（含未分配265），该数不适用于现行跨店铺去重口径，也不是固定验收数；任务成功后刷新统计取最新数据。

## 口径

- 数据源：Python配置库中的 `ods_lingxing_amz_listing_latest`（本地date-project），只统计status=1且is_delete=0，接口 `/erp/sc/data/mws/listing`。原始表保留全部状态，不在抽取时过滤。店铺映射仍取shop_source_database，不受补货仓库和公式限制。
- 批量读取 `shop_list`（限定平台 `10001`）后按 sid 字典匹配店铺名称。两表 sid 类型不同，直接 SQL JOIN 会发生 double 转换并逐行扫描；本实现避免该开销，无逐行查库。负责人不使用 Listing 的 `principal_name`。
- 按中国时区当前月份读取 Python 库 `dwd_performance_owner_rule` 的 amazon 规则，不取最大月份（规则可能预先导入未来月份）。
- 直接复用绩效服务 `_amazon_principal` 和 `_amazon_store_rules`：EU-UK 固定负责人；EU OTH 按第二段、其他 EU 按品牌；非 EU 按店铺第二段；保留重庆茁凯的既有别名回退。
- 先按当月规则匹配负责人，再按 `(负责人, 去空白并大写的完整seller_sku)` 去重。同一负责人跨店铺同一卖家SKU只计一次；不同负责人各自计数；同一本地SKU对应多个不同seller_sku分别计数，不按中间码合并。本地SKU仅用于原有品牌/OTH匹配，不再充当统计去重键。
- 未匹配保留为“未分配”（橙色）；缺店铺名称也进入未分配。只有缺seller_sku时不计入并提示，不回退为local_sku。缺本地SKU的US记录仍按店铺匹配；EU非英国站缺本地SKU时无法匹配品牌，进入未分配。
- 2026-09-18 口径修正验收：袁巾茹9月四个店铺对应12个sid，当前81条在售刊登，seller_sku跨店铺去重为43。原按sid＋local_sku得到74（US 40＋CA 34），已改为43。不修改源表、其他报表或eBay逻辑，无需SQL。

## 调用及权限

- Vue：首页 `Index` → `AmzOwnerSkuChart` → `GET /operations/amz/owner-sku/summary`。
- Java：`AmzOwnerSkuController` → `PerformancePythonClient` → `GET /api/v1/finance/amz-owner-sku/summary`。
- Java 校验 `operations:amzReplenishment:list`，Vue 无权限不挂载图表、不发请求；Python 校验现有内部 Token。
- 刷新统计仅重新查询源表，不拉取领星数据，不改绩效或补货结果，不写数据库。

## 完整性与边界

一次只读一致性事务读取新刊登、店铺、当月规则和成功发布状态。ods_lingxing_amz_listing_state未初始化时返回SOURCE_NOT_READY；数据和标记原子发布，同步失败时继续读上一批完整快照及其时间，不再依赖旧Java data_sync_log。缺当月规则时显示提示而非零。

2026-09-18 最终采用隔离方案：原Java同步完全恢复sid、is_pair=1、is_delete=0、offset、length=1000，继续供AMZ补货使用。新Python同步只传sid和分页，完整原始行写入新表，不改变旧表唯一键或原补货SQL。首页改读新表并过滤status=1且is_delete=0。

首次新源发布后验收：60,681条原始记录，18,659条status=1中排除772条已删除记录，最终读取17,887条。当前9月规则统计如下（跨店铺按负责人+完整seller_sku去重，不是原始行数）：

| 负责人 | SKU数 |
| --- | ---: |
| 吴清栩 | 1714 |
| 陈渝 | 780 |
| 赵昕怡 | 654 |
| 唐倩 | 538 |
| 陶俊霏 | 527 |
| 胡薇 | 425 |
| 张生敏 | 295 |
| 袁巾茹 | 292 |
| 毛静 | 211 |
| 徐倩 | 174 |
| 王皓 | 107 |
| 李茫茫 | 97 |
| 未分配 | 402 |
| 注销（负责人规则原值） | 1 |

计数之和6,217。同一SKU可分别归属不同负责人，因此不能当作全平台唯一SKU数。“注销”是现有规则文字，不是真实人员，本次不擅自删除已匹配项。该结果仅对应2026-09-18 15:06:27拉取批次，后续源数据或规则更新会变化。修改后需重启Python；无需SQL、无需再次拉取、不影响AMZ补货和eBay图表。

旧Java对缺失/非法status默认填1的行为未动；新Python源不这样兜底，状态缺失或非法时失败保留上批。新源首次拉取完成后核对12个sid及在售数量，不把旧表数量当作验收常量。

## 部署

执行 ../deploy/amz-listing-raw/ 中01建表与Python任务、02登记Quartz任务两个SQL，重启Python和新版Java。无需新增菜单权限，沿用AMZ补货查看权限。手动执行新任务“领星-AMZ刊登原始数据每周同步”后刷新首页；不要混淆原“领星-Amazon商品刊登”任务。

## 验证

在 Date-Project 目录：`.venv/Scripts/python.exe -m pytest tests/test_amz_owner_sku.py tests/test_performance_owner_matching.py -q`。

前端：`node --test tests/home-shell.test.mjs tests/amz-owner-sku-chart.test.mjs`，`npm run build:prod`。

Java：`mvn -pl ruoyi-admin -am -Dtest=AmzOwnerSkuControllerTest -Dsurefire.failIfNoSpecifiedTests=false test`，覆盖无权限拒绝、有权限放行、响应解包与请求追踪。

早期旧口径本地只读实测：在售刊登16,392行，按sid＋local_sku去重后15,850个店铺SKU；12位已匹配负责人、未分配47个。源表更新时间2026-09-17 12:07:24，规则月份2026-09。该历史结果不适用于现行seller_sku跨店铺去重口径，不是实时领星数据或固定验收常量。

性能：直接 sid JOIN 实测约3,988ms；改为两次批量取数及字典匹配后，完整统计服务两次实测136ms、120ms，数量一致。无新增索引、DDL或数据写入。
