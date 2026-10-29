# Amazon补货建议拉取优化

## 参数与写入

- 接口：`POST /erp/sc/routing/restocking/analysis/getSummaryList`。
- 保持 `data_type=2`、`mode=0`，分页 `length=50`，偏移量按实际返回的主记录数递增。
- 默认将全部有效Amazon店铺一次传入 `sid_list`，减少共享库存跨店铺批次的重复请求。需要分批时可设置 `LINGXING_RESTOCK_SID_BATCH_SIZE=10`；0代表合并，负数拒绝执行。
- 保留父节点和国家子节点。总数异常时整轮重读，最多三轮；所有轮次共用90分钟拉取预算。失败不替换业务源表，全部拉取通过后事务全量覆盖。

## 超时和进度

- job215补货建议由30分钟改为90分钟，独立任务的分组锁由45分钟改为105分钟；其他独立任务仍为30分钟。
- AMZ链路中的补货步骤也改为90分钟。步骤锁覆盖重试预算，AMZ链路锁按各步骤最大预算计算，正常结束立即释放。人工AMZ全量同步的分组锁增加90分钟预算；仅刷新快照的锁不变。
- 首屏、每10页、最后一页记录当前轮次、主记录已读/总数、父子节点数量、耗时和估算剩余时间；进入源表替换、同步完成各记录一次日志。
- 调整代码和配置不会改变已启动任务；重新打包、重启Java后生效，不需要SQL迁移。

## 2026-10-29只读验证

133家有效店铺合并查询，抽查offset为0、50、100、12900、25800，最后再检查offset=0，均返回成功且total=25809；尾页9条。首次读取的各抽查页面没有重复主记录。此结果是抽页验证，不代表整轮517页已完成。

按当时接口报告总数，原10店铺分批需要约641页，合并后约517页，减少约19%的分页请求。接口耗时、数据变化和重试仍会影响实际运行时间，90分钟是上限而不是预估耗时。

## 混销Amazon库龄来源

库龄使用另一个接口：`POST /basicOpen/openapi/storage/fbaWarehouseDetail`，请求包含 `query_fba_storage_quantity_list=true`。Python `clearance_service.sync_fba_inventory` 保存到 `ods_lingxing_amz_fba_inventory_raw`，混销读取该表最新整体月份。

`inv_age_0_to_90_days`、`inv_age_91_to_180_days`、`inv_age_181_to_270_days`、`inv_age_271_to_365_days`、`inv_age_365_plus_days` 都是各库龄段的库存数量。混销显示数量大于0的最高区间，不将数量当成天数，也不把区间上界当精确库龄。
