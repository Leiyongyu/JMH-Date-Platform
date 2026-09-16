# Ebay库存历史透视：部署说明

## 一、用途与范围

在“运营中心 → eBay → Ebay库存明细”切换明细与历史透视视图。历史透视按“负责人＋站点＋统计日期”保存12列：负责人、站点、统计时间、SKU数、海外可售、海外总库存、近30天销量、可售库销比、总库销比、海外可售货值、海外总货值、30天谷仓仓租。

历史数据来自生成时完整的库存明细计算结果，不受用户当前页面筛选、分页或勾选限制；查询历史只读已保存汇总，不重新匹配今天的负责人、单价或仓租。未匹配负责人保留“未分配”，不能丢掉这部分库存。

本次不修改补货2.0，不修改原月度库存或月度库龄口径，不创建新的Quartz任务，不新增菜单权限。列表与导出复用已有 `operations:ebayInventoryDetail:list` / `operations:ebayInventoryDetail:export` 权限。

## 二、统计时间与保留规则

- **统计日期 `stat_date` 是实际生成时的中国时区日期，显示 `YYYY-MM-DD`。** 同时保存 `stat_month` 方便按年月整理；年月不能替代日期，否则一个月内的每周变化无法区分。
- 同一天再次成功生成，在同一事务内更新该日期的快照头并替换其汇总行；不新增重复日期、不累加旧值。**不同日期永久保留**，没有按月或按条数自动清理。
- `generated_at` 记录实际生成时间；`inventory_snapshot_date`、`inventory_pulled_at` 另行记录库存源的日期和拉取时间。统计日期不表示所有数据源都在当天刷新过。
- 统计时间筛选只能返回真正保存过的日期。选择起止区间不会自动补出中间未生成的日期，也不会伪造过去的库存。
- 不允许通过手动日期参数创建或覆盖过去的统计日。首次部署不回填旧周数据；当前源表只保留最新批次，无法重建真实历史。
- 周报源ODS清理旧批次、删除已生成的Excel文件，不删除历史透视表。

## 三、计算口径

所有数据沿用库存明细相同的7个仓库、最新成功库存批次、同仓同产品整行去重及站点匹配口径。

| 透视字段 | 口径 |
|---|---|
| 负责人、站点 | 冻结生成时的负责人分配及站点；同一负责人不同站点分别汇总 |
| SKU数 | 每个负责人、站点下完整SKU去重计数，不去品牌前缀 |
| 海外可售、海外总库存、近30天销量 | 对对应明细值求和；近30天沿用订单源全表最新付款日锚点，并非强制改成统计日倒推 |
| 可售库销比 | 海外可售合计÷近30天销量合计；分母为0返回0 |
| 总库销比 | 海外总库存合计÷近30天销量合计；分母为0返回0 |
| 海外可售货值、海外总货值 | 对未舍入的明细金额求和，最后 `ROUND_HALF_UP` 保留2位人民币金额；不是先逐SKU舍入再累加 |
| 30天谷仓仓租 | 对库存明细中已按当批拉取月份汇率折成人民币的未舍入仓租求和，最后 `ROUND_HALF_UP` 保留2位 |

比率按汇总后的分子、分母重算，不平均或累加SKU比率。数据库保存原比值，页面和Excel按百分比显示，不再次乘100后存库。

金额缺失按用户确认的口径排除：各项金额只汇总有值的SKU，不因部分缺价、仓租缺失或匹配冲突而将整组清空。该项金额全部缺失时才保存 `NULL`，页面和Excel显示 `--`；真实0金额正常计入。仍保存 `missing_price_count` / `missing_rent_count`，页面提示已排除的SKU数量。仅排除对应金额，不移除该SKU的库存、销量或SKU计数。

本次仅调整汇总代码，不需要新增字段或再次执行建表SQL。已冻结的跨日期历史不重算；旧口径生成的NULL不会被伪装成0或当前汇总值。新快照的metadata_json带有 `amount_aggregation_policy=sum_present_v1`，用于区分口径。

## 四、建表SQL

执行文件：`Date-Project/migrations/20260916_ebay_inventory_pivot.sql`。

执行库为Python数据库 **`date-project`**，不是Java默认库 `jmh_data_platform`。脚本自带 `USE` 和 `SET NAMES utf8mb4`，只包含两条 `CREATE TABLE IF NOT EXISTS`：

| 表 | 用途 |
|---|---|
| `ebay_inventory_pivot_snapshot` | 一个统计日一条快照头，保存源批次、生成时间、明细/汇总数量及来源元数据JSON |
| `ebay_inventory_pivot_owner` | 负责人＋站点的冻结汇总；外键指向快照头 |

没有 `DROP`、`TRUNCATE`、业务数据 `DELETE` / `UPDATE`，没有新任务或菜单数据。重复执行不会覆盖已有历史；**CREATE IF NOT EXISTS不会修正已存在的不一致结构**，遇到历史环境结构差异应先核查，不能删除表重建。

部署机使用已配置好的数据库工具导入本文件即可；不要把密码写进命令或文档。不能把整个 `schema.sql` 当作本次增量部署脚本执行，因为它还包含其他模块的初始化数据。

建表后只读核验：

```sql
SHOW CREATE TABLE `date-project`.ebay_inventory_pivot_snapshot;
SHOW CREATE TABLE `date-project`.ebay_inventory_pivot_owner;

SELECT table_name, engine
FROM information_schema.tables
WHERE table_schema = 'date-project'
  AND table_name IN ('ebay_inventory_pivot_snapshot', 'ebay_inventory_pivot_owner');
```

两张表均应为InnoDB；快照头有 `stat_date` 唯一键，明细有 `(snapshot_id,owner,site)` 唯一键与外键。首次创建后0行正常，建表不生成历史。

## 五、部署与首次生成

1. 先在部署数据库执行上述增量建表SQL。
2. 部署本轮Python与Java代码；Java新增历史查询/导出代理需要重新编译并重启，Python未启用reload时重启。
3. 构建并部署 `RuoYi-Vue3-master` 前端，刷新浏览器。
4. 确认已有成功周报库存快照及库存明细所需来源。缺失金额不参与合计，有效金额正常累加；某项金额全部缺失时为NULL，不会凭空补值。
5. 本地首次验证可在 `Date-Project` 目录执行下列命令，仅生成**执行当天**的一份历史记录；不调用领星或谷仓，不重拉库存，不回填往日。部署机是否执行首份生成由部署人员决定，SQL本身不会执行它。

```powershell
.venv/Scripts/python.exe -c "from backend.services.ebay_inventory_pivot_service import capture_snapshot; print(capture_snapshot(trigger_type='BOOTSTRAP'))"
```

`BOOTSTRAP` 只是记录触发来源，不表示历史回填。如果当前库存快照是几天前，首份统计仍使用今天日期，并保留真正的源库存日期/拉取时间。不要把首份记录描述成今天重新采集的库存。

**执行记录约束：本说明中的命令与检查项是部署步骤，不代表已在部署机执行。** 本地实际执行结果应以操作者回报、表内记录及测试日志为准。

## 六、自动生成与失败处理

原任务 `pythonWeeklyInventoryTask.runWeekly()`（当前每周一07:30）保持原调度配置。它先完整拉取、校验并生成Excel，再事务提交周报ODS和成功登记；之后调用历史捕获，并校验使用的 `inventory_batch_id` 必须就是该次新发布批次。

- 新历史保存成功：任务返回 `pivot_snapshot`，包含统计日、快照ID、负责人站点组数、明细数等。
- 拉取或周报发布失败：不生成本轮历史。
- 历史保存失败：历史写事务回滚，之前已保存的历史保留；**已成功发布的库存源和Excel不回滚，也不改成FAILED登记**。任务仍抛出明确异常并告警：`库存和Excel已成功发布，但历史透视保存失败`，避免静默漏掉某周。
- 此时先修正历史失败原因，再执行保存命令重试；无需为了补历史反复调用上游接口。同日重试覆盖当日记录，跨日重试只能记录新的实际日期，不能冒充失败当天已生成的历史。
- 脚本菜单的“仅使用现有数据生成Excel”不调用历史捕获；普通页面查询和导出也不写历史。

## 七、只读验收

```sql
SELECT id, stat_date, stat_month, generated_at,
       inventory_snapshot_date, inventory_pulled_at,
       inventory_batch_id, trigger_type, item_count, group_count
FROM `date-project`.ebay_inventory_pivot_snapshot
ORDER BY stat_date DESC;

SELECT h.stat_date, o.owner, o.site, o.sku_count,
       o.overseas_sellable_quantity, o.overseas_total_quantity,
       o.sales_qty_30d, o.in_stock_sales_ratio, o.total_stock_sales_ratio,
       o.overseas_sellable_value, o.overseas_total_value, o.warehouse_rent_30d_cny,
       o.missing_price_count, o.missing_rent_count
FROM `date-project`.ebay_inventory_pivot_snapshot h
JOIN `date-project`.ebay_inventory_pivot_owner o ON o.snapshot_id = h.id
ORDER BY h.stat_date DESC, o.owner, o.site;

-- 期望0行：头部计数必须与实际汇总一致。
SELECT h.id, h.stat_date, h.item_count, SUM(o.sku_count) actual_items,
       h.group_count, COUNT(o.id) actual_groups
FROM `date-project`.ebay_inventory_pivot_snapshot h
LEFT JOIN `date-project`.ebay_inventory_pivot_owner o ON o.snapshot_id = h.id
GROUP BY h.id, h.stat_date, h.item_count, h.group_count
HAVING h.item_count <> COALESCE(SUM(o.sku_count), 0)
    OR h.group_count <> COUNT(o.id);
```

重点验收：同日生成两次仍只有一个日期、跨日旧记录不变；当前源或负责人配置改变不会回算旧历史；零销量的比率为0；部分缺失时金额等于有效SKU金额之和，全部缺失时为空，真实0有效，缺失数正确；日期区间只返回真实历史；透视页面与Excel一致；仅生成Excel不会新增历史。

## 八、本地执行记录（2026-09-16，非部署机）

已在本地数据库执行上述迁移两次，两张表首次创建、第二次保持不变。未执行其他模块schema，不删除原库存或仓租数据。

已从当前数据生成 `2026-09-16` 首份快照，并同日重跑验证覆盖：快照ID保持1，库存明细2670行、负责人站点汇总12行、日期数量1。源库存快照日期为2026-09-16，拉取时间10:47:49；历史生成时间11:24:09。本操作只读取数据库，没有重新调用领星或谷仓。

首轮12行站点汇总覆盖全部2670条明细，其中21条缺价、12条仓租匹配缺失或冲突；首轮曾按“任一缺失则整组NULL”生成。后续用户确认改为仅汇总有效金额，代码、页面提示与文档已同步。今日记录按新口径覆盖，跨日历史不改；当时Excel校验为12数据行、12列。新增跨站点负责人汇总后，导出还会增加红色汇总行，见下节。

部署目录配套文件：`18_Ebay库存历史透视建表.sql`、`部署说明_Ebay库存历史透视.md`。部署机需另执行该增量SQL和部署新版代码；本地执行不代表部署机已执行。

## 九、每个快照的负责人红色汇总

每个“统计日期＋负责人”的站点明细后追加一条 **负责人汇总**，整行红色加粗；Excel同步导出红字汇总。勾选“仅看负责人汇总”可在页面隐藏站点明细，便于对比同一负责人每周的变化；该开关不改变导出范围，导出仍包含全部筛选结果的站点明细和汇总行。

- 数据只来自已经冻结的 `ebay_inventory_pivot_owner`，不会重新读取实时库存、单价或负责人规则，也不会改写历史表。不需要新建表、重跑快照或额外授权。
- 以 `(stat_date, owner)` 为组跨站相加。日期、负责人、站点筛选先作用于明细，再求和；筛选某站点时只汇总该站点，不混入未选站点。
- SKU数是各站点SKU数之和，即“站点＋SKU”记录数。同一SKU在不同站点分别计数，不声称跨站去重（已保存的汇总表不含SKU清单）。
- 海外可售、海外总库存、近30天销量、缺失数量直接求和。金额对已冻结站点金额求和，忽略NULL，全部NULL才显示 `--`，真实0正常保留；不从当前原始数据倒算旧金额。
- 两个库销比分别使用该负责人的“汇总可售／汇总销量”和“汇总总库存／汇总销量”，零分母为0；不平均或相加站点百分比。
- **分页单位改为负责人日期组**。一组的全部站点明细和汇总行始终同页；`page_size=50` 表示50组，不是50个站点行。接口 `pagination.total` 是组数，`metadata.detail_count` 是匹配站点行数，`metadata.owner_total_count` 是匹配组数，`metadata.pagination_unit=owner_date`。
- 排序按负责人汇总指标排序；组内站点按名称排序、汇总行置于组末。页面红色汇总行标记 `row_type=OWNER_TOTAL`，站点明细标记 `DETAIL`。默认统计日期倒序，再按负责人稳定排序。
- 导出上限50000行同时包含站点明细与负责人汇总。核对金额时，**不能再次把明细与红色汇总一起相加**，否则重复计数。

本次为Python查询、前端渲染和Excel格式修改，Java接口参数与权限保持不变。部署更新Python并按运行模式重载/重启，重新构建部署前端即可；不执行历史数据更新SQL。

本地只读验证（2026-09-16）：12条站点记录组成4组负责人，接口和Excel均返回12条明细＋4条红色汇总＝16行；逐组核对数量、缺失计数、金额和重算比率均一致。按每页1个负责人组翻页无重复或遗漏，站点筛选只汇总所选站点；查询和导出前后两张历史表内容指纹完全一致，未写入数据。
