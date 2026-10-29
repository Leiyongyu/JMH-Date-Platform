# 混销 Amazon 30 天销量来源（2026-10-29）

混销 Amazon 汇总、展开的店铺明细，以及 eBay 站点明细中的 Amazon 对比销量，统一读取领星 `/erp/sc/data/mws/listing` 返回的 `thirty_volume`。

## 取数规则

- 数据表为 Python 库（本项目配置为 `date-project`）的 `ods_lingxing_amz_listing_latest`。
- 仅使用 `ods_lingxing_amz_listing_state` 中 `id=1` 指向的成功发布批次，排除 `is_delete=1` 的刊登。停售但未删除的刊登仍可贡献近 30 天销量。
- 沿用现有渠道与仓库 SKU 映射，按店铺 `sid`＋完整 `seller_sku` 精确匹配，MSKU 区分大小写，不截断前缀或后缀，不跨店铺匹配。
- `thirty_volume` 在数值校验后转换为 `DECIMAL(24,6)`；同一店铺/MSKU 若有重复原始行，取最大有效值一次，再汇总到店铺、站点及仓库 SKU，避免重复累加库存或销量。
- 无源记录、空值、负数或非法数值保持为空，真实的 0 保留。没有成功发布批次时销量为空，不回退补货建议。
- 页面“销量同步时间”取成功批次的 `pulled_at`。该值是刊登同步时接口返回的滚动 30 天销量；刷新页面只重读已保存数据，不触发领星全量拉取。

## 刷新与部署

刷新销量使用已有任务“领星-AMZ刊登原始数据每周同步”，Java 调用目标 `pythonAmzListingRawTask.runWeekly()`，Python 任务代码 `lingxing_amz_listing_raw_sync`。仓库中的默认计划为每周四北京时间 10:00，部署环境实际计划以定时任务配置为准。

发布 Python 修改并重启服务，构建并发布前端以更新来源提示。此次改动不需要表结构变更或重算补货建议；若部署库尚无原始刊登表和成功批次，请按 `deploy/amz-listing-raw/部署说明.md` 部署已有采集链路并手动同步一次。

混销请求由 Java `AmzMixedSalesController` 转发到 Python，实际共享取数逻辑位于 `backend/services/mixed_sales_sql.py`。
