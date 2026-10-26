# 下线eBay补货1.0

## 本次范围

- 移除1.0列表页面、前端API模块、独立月销预测公式页面及旧控制器。
- 移除1.0专用查询、筛选、导出、产品性质修改及公式编辑HTTP接口。
- 移除对应服务中的查询逻辑、旧导出实现及Mapper中无调用的查询/写入方法。
- 原销量、利润率、退货率上传迁到“eBay跟价”的导入菜单。新接口分别为
  `POST /operations/ebay/price-tracking/import-sales`、`import-profit-rate`、`import-return-rate`。
  文件格式、写入目标和原`operations:ebayReplenishment:import`权限保持一致。
- 补货2.0的页面、接口、Python计算、人工配置、采购和权限均保留。

## 保留的共用部分

跟价在计算及刷新后补写时仍读取`ebay_replenishment_snapshot`，分别使用历史采购建议量和最大月销补货量。
本轮保留其内部计算、快照、公式表和任务执行顺序，避免跟价补货量变成旧数据或改用未经确认的2.0公式。
保留的`IEbayReplenishmentSnapshotService`仅有内部`refreshSnapshot()`，已无补货1.0用户接口。

不删除`ebay_replenishment_snapshot`、`ebay_replenish_formula`，也不删除
`ebay_product_dedup`、`ebay_sales`、`brand_owner`、刊登、库存、采购、谷仓及日志等共用表。
未清理本轮范围外的2.0历史仓租上传表或参数表。

`EbayReplenishmentSearchRequest`、`ExportRequest`、`OperationImportService`、
`UnifiedExportService`仍被跟价、AMZ等使用，只删除其中1.0专用分支。
`operations:ebayReplenishment:list/import/export/sync`仍被其他功能使用，不能批量撤销角色权限。

## 部署

1. 在Java ERP数据库执行`RuoYi-Vue-springboot3/sql/20261024_retire_ebay_replenishment_v1.sql`。
   脚本将旧菜单转成非路由权限节点，保留原menu_id和角色授权；旧公式页面停用。
   不操作补货2.0菜单和权限，不修改库存/订单数据，也不删除业务表。
2. 使用`mvn clean package -DskipTests`重新打包并重启Java，构建和部署前端。
   使用clean构建以移除旧控制器的历史class文件。Python未修改，无需因此重启。
3. 退出重新登录，确认旧补货及旧公式页面不再出现；跟价、同步和补货2.0正常可用。

本次代码改动不会自动执行SQL。仅重启不会清理数据库中的旧动态菜单，必须执行菜单脚本。
后续不要重新执行旧菜单初始化脚本，以免恢复已经下线的路由。
菜单脚本可以重复执行；已经转换的节点不会再次被当作旧页面。

## 回归重点

- 补货2.0：列表、负责人/等级筛选、刷新、导出、运营/开发备注、运营确认、采购权限。
- 跟价：查询、导出、共用数据导入、预估补货量及同步刷新。
- 原共用权限用户仍能访问跟价和数据同步；无需给普通用户新增2.0权限。
- 旧`/operations/ebay/replenishment/**`接口不再注册。

如以后需要彻底移除保留的内部历史补货计算，应先确定跟价“预估补货量”的替代口径，
再修改跟价的两处读取及同步任务，最后另行审批数据库表的备份和删除。
