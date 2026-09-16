# Ebay库存明细历史：部署与使用

## 口径

- 统计日期采用实际生成时的中国时区日期（YYYY-MM-DD），不是源数据拉取日期。
- 一日一个共享批次：复用 ebay_inventory_pivot_snapshot.stat_date 的唯一键。
- 新增明细表 ebay_inventory_detail_history，按 snapshot_id + site + sku 唯一。
- 每次生成完整冻结所有 SKU 的29个展示字段（含中间码和统计日期），以及字段异常提示；缺失仍为NULL，Decimal精度不转float。
- 统计日期保存在共享主表，读取时投影到每条明细；JSON保存当时的业务计算值。
- 同日重新生成：主表、负责人透视、全量库存明细同一事务覆盖；写入失败整批回滚。其他日期长期保留，不随ODS清理。
- 查询或导出不生成快照，不用最新库存、负责人、等级、汇率、单价重新计算历史。
- 页面默认最新已保存明细日期。日期选择器只允许选择已保存明细的日期，分页与导出固定使用已选日期，切换日期清空勾选。
- 等级导入更新配置表，不回写已有历史；下一次生成快照时生效。
- 页面右上角“刷新”现为显式写入操作：读取所有当前已落库来源重新计算，覆盖今天的明细和透视快照；完成后切回今天并清空勾选、回到第一页，不受当前站点/SKU/等级筛选限制。
- 刷新不会调用领星或谷仓接口；即使选中旧日期，也不会覆盖旧日期。连续点击在前端禁用，服务端沿用快照互斥锁；失败回滚保留已有快照。
- 查询、筛选、分页、排序、打开页面和浏览器刷新仍只读；仅点击表格工具栏的刷新图标才生成快照。
- 写接口为POST /finance/ebay-inventory-detail/snapshot/recalculate，复用operations:ebayInventoryDetail:import权限（和产品等级导入相同），有UPDATE审计；仅查看权限不能覆盖全局历史。无需新增权限SQL。

## 上传后操作

接口任务完成 → 上传销量、负责人或产品等级等所需数据 → 点击库存明细右上角刷新 → 用最新来源重新计算并保存今天明细和透视 → 自动显示今天。
同一天反复刷新只覆盖同一日期批次，不累加重复记录。历史透视自身的查询刷新仍只读。

## 执行SQL与部署

1. 已有18号历史透视两表是前置条件；未建先执行18_Ebay库存历史透视建表.sql。
2. 执行19_Ebay库存明细历史建表.sql（与仓库 Date-Project/migrations/20260916_ebay_inventory_detail_history.sql 内容一致）。
3. SQL在 date-project 数据库仅新增一张表；无DROP、TRUNCATE、DELETE、UPDATE。可重复执行，不覆盖已有数据。
4. 部署Python、重新编译并重启Java、构建并部署Vue前端。无需新菜单权限或新增Quartz任务。
5. 现有 job251 仓位库存明细周报成功后，原capture_snapshot链路会自动同时冻结明细与透视。
6. 首次生成或手动同日更新可在Date-Project目录执行：

```powershell
.venv/Scripts/python.exe -c "from backend.services.ebay_inventory_pivot_service import capture_snapshot; print(capture_snapshot(trigger_type='BOOTSTRAP_DETAIL'))"
```

上方命令仅查询已落库的现有来源，不调用外部接口、不重拉库存、不补造过去。
同一天已有快照会整体覆盖，包括负责人透视；其他日期不变。
只有旧透视汇总、没有当时完整明细的日期，不能反推明细，因此不会出现在明细日期选择器中。

## 核验

```sql
SELECT s.stat_date,s.id,s.generated_at,s.inventory_batch_id,s.item_count,
       COUNT(d.id) AS detail_count
FROM `date-project`.ebay_inventory_pivot_snapshot s
LEFT JOIN `date-project`.ebay_inventory_detail_history d ON d.snapshot_id=s.id
GROUP BY s.id ORDER BY s.stat_date DESC;

-- 以下两条应无重复行
SELECT stat_date,COUNT(*) FROM `date-project`.ebay_inventory_pivot_snapshot
GROUP BY stat_date HAVING COUNT(*)>1;
SELECT snapshot_id,site,sku,COUNT(*) FROM `date-project`.ebay_inventory_detail_history
GROUP BY snapshot_id,site,sku HAVING COUNT(*)>1;
```

历史列表和导出沿用原路径，增加 statDate（Java）/ stat_date（Python）参数。
取最新已保存明细可传latest；界面拿到实际日期后将分页和导出固定到该日期。
内部服务不传日期时保留原实时计算路径供兼容调用，页面不会走该路径。

## 本地执行记录（2026-09-16）

- 已执行本脚本，新建 date-project.ebay_inventory_detail_history。
- 已生成2026-09-16首份明细：snapshot_id=1，2670条明细、12条负责人站点汇总。
- 同日重新生成后snapshot_id仍为1、明细仍2670条；统计日期和明细键无重复。
- 真实历史查询首页约0.14秒；所选1条Excel导出29列，统计日期正确。
- 目前只存在2026-09-16的明细历史，没有补造过去日期。跨日期保留与失败回滚使用隔离测试覆盖。
- Python相关测试278项、前端相关测试52项、Java相关测试14项通过；前端生产构建通过。
- 本轮没有重启运行中的服务；部署或本地使用新页面前需加载更新后的Java、Python和前端。

## 主动刷新重算补充验证（2026-09-16）

- Python回归280项、前端回归58项、Java回归21项通过。
- 覆盖：点击刷新只发一次POST、不能传历史日期或筛选来改写快照、返回服务器今天后切换列表、失败不报成功、不重试写入、缺写权限被拒绝。
- 本次未新增数据库结构或执行SQL；沿用已经执行的19号建表脚本。新接口需加载更新后的Java与Python，前端需部署新版构建。
