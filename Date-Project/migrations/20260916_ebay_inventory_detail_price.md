# Ebay库存明细：上传单价与最低价匹配（2026-09-16）

## 本次口径
- 单价不再读取领星产品管理的 cg_price；仅使用独立上传表 `date-project.ebay_inventory_detail_price`。
- 兼容《产品单价明细表.xlsx》的“产品代码”“单价(默认采购价)”列。SKU自动去首尾空格并转大写；自动保存中间码（第二段纯数字，保留前导零），不按站点匹配。
- 文件内按完整 SKU＋价格去重。同一中间码有多价时取当前已上传数据的 **MIN(unit_price)**，包括明确的0。人民币原值，无换汇或加税。
- 同一SKU允许多价。重复上传按文件涉及的SKU **替换该SKU的整组价格**，其他SKU完全保留。不是把所有历史低价一直累积，因此从10改为20并重传后，该SKU旧10元会被移除；同中间码其他SKU仍保留的更低价仍参与最低值。
- 非数字中间码（如IDD-LMM-…、GM-40031B-…）的价格行保留，但中间码为空，不参与自动匹配；结果返回警告。不会猜测截取下一段数字。
- 非法价格、负数、非有限值、超出存储精度等会整份拒绝，数据库不做部分写入。空白行忽略。
- 货值＝中间码最低原价×库存，使用未舍入Decimal，最终金额保留2位。替代以前的库存加权单价口径。库存/销量/仓租及仓库范围不变。

## 部署
1. 备份后，在Python数据库执行同目录 `20260916_ebay_inventory_detail_price.sql`。仅CREATE TABLE IF NOT EXISTS，不删表、不初始化示例价格、不覆盖数据。
2. 部署Python、重新编译启动Java、部署前端构建。
3. 复用 `operations:ebayInventoryDetail:import` 权限，无需新增菜单或权限SQL。无该权限不能上传。
4. Ebay库存明细 → **导入产品单价** → 上传文件，核对去重行数及无法解析中间码的警告。
5. 点击页面 **刷新**：重新计算今日明细与负责人透视，同日覆盖同一日期批次；历史日期不回写。单价导入本身不改快照，不拉外部接口。

## 接口
- Java：POST `/finance/ebay-inventory-detail/prices/import`，multipart file，导入权限与审计。
- Python：POST `/api/v1/finance/ebay-inventory-detail/prices/import`，仅内部访问；operator由Java取当前用户名。
- 写入在事务内按SKU分批替换，命名锁拒绝并发导入；异常回滚，避免留下半份价格。刷新使用一致性读，不混用替换前后的数据。

## 核对SQL
```sql
SELECT middle_code, MIN(unit_price) AS selected_cny_price, COUNT(*) AS source_rows
FROM `date-project`.ebay_inventory_detail_price
WHERE middle_code IS NOT NULL
GROUP BY middle_code;

SELECT sku, unit_price, source_file
FROM `date-project`.ebay_inventory_detail_price
WHERE middle_code IS NULL;
```

实际匹配只用文本中间码，“010053”和“10053”不是同一个键。
尚未导入或匹配不到单价时，价格和货值显示--，绝不回退产品管理的旧价格。

## 本地执行记录（2026-09-16）
- 经用户确认，已在本地date-project执行同目录建表SQL，新建独立单价表。
- 已导入《产品单价明细表.xlsx》：18,922行，文件内合并10,278条重复，保存8,644个SKU＋价格组合，8,624个完整SKU，5,296个有效中间码。
- 191条源行（去重后92个SKU）无法提取纯数字中间码，保留价格行、中间码NULL，不参与匹配；6个中间码最低价为有效0。
- 只读实时计算核对：库存1,926组，1,915组有匹配单价，11组无价显示--；全部价格与SQL的MIN相符，两项货值逐行复算一致。
- 未重写历史快照、未启动外部同步、未重启服务；需要加载新代码后点击页面刷新才会覆盖今日快照。
