# eBay补货2.0参数配置部署

1. 在Java ERP使用的 `jmh_data_platform` 数据库执行同目录的 `20260928_ebay_replenishment_v2_parameters.sql`。
2. 部署并重启Java后端，更新Vue前端。
3. 打开eBay补货2.0，在“重置”右侧点击“参数”。四个模块分别为基础参数、形态权重、等级下限分、维度权重，均以三列表格展示。

SQL可重复执行，只补充缺少的参数，不覆盖已有值。训练期天数已由Python读取，用于追加的ADI列，部署时须同步更新Python服务。

## 权限与接口

- `GET /operations/ebay/replenishment-v2/parameters`：复用 `operations:ebayReplenishmentV2:list`，返回 `data.modules`、`data.values`、`data.revision`。
- `PUT /operations/ebay/replenishment-v2/parameters`：复用 `operations:ebayReplenishmentV2:formula`。请求为 `{ "revision": "读取时返回的版本", "values": { "prior_days": "30", "...": "..." } }`，须提交全部62个键。操作者从登录态取得。
- 无公式权限时可查看，不能编辑。无需新增菜单或分配新权限。

## 数据约定

表 `ebay_replenishment_v2_parameter` 按稳定参数键保存全局配置。基础28项、形态15项、等级5项、维度14项，共62项。数字用 `DECIMAL(18,6)`，等级用 `text_value`。参数目录、默认值、原始说明位于 `ruoyi-system/src/main/resources/ebay/replenishment-v2-parameters.json`。

比例按小数保存，例如30%存0.3；开关存0/1；`negative_margin_grade` 保存S/A/B/C/D；`prior_demand_rate` 允许NULL，为后续自动推算预留。其余数值必填。k先验天数使用 `prior_days`，K先验件数使用 `beta_prior_quantity`，避免数据库不区分大小写导致两者混淆。

训练期天数等目前是人工参数，不自动推算。ADI已读取 `training_days`：有单天数为0时为999，否则为训练期天数÷有单天数。保存参数后自动刷新页面。附件说明中的其他历史月份、版本结论、计算描述作为原始参考保留；现有预测、等级和补货公式暂不读取本表。

保存前校验数值范围、小数位数、阈值顺序、等级顺序、形态权重合计（1，无销量也可全0）和全部维度权重合计（1，包括未启用项）。四个模块在同一事务内保存，基于版本和行锁防止旧弹窗覆盖新配置。恢复默认只修改弹窗草稿，点击保存后才写库。

## 验收

- 检查四个模块默认值，分别修改并保存，关闭后重新打开应保留修改。
- 取消不写库，未保存关闭时提示；恢复默认后取消不写库。
- 无公式权限的账号只读；直接调用PUT也由后端拒绝。
- 两个弹窗读取同一版本，第一个保存后，第二个提交旧版本应提示重新打开。
- 缺项、非法数字、小数天数、错误权重和等级顺序应拒绝整份保存。

本地已验证默认值匹配、SQL幂等、定点数字存取及测试修改回滚；6项服务单元测试、Java依赖链编译、Vue生产构建通过。真实登录页面的端到端交互仍需重启后端后验证。
