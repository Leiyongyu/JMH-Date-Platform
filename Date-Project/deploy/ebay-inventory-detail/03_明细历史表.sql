-- 先执行20260916_ebay_inventory_pivot.sql建立共享日期批次主表。
-- 仅新增明细历史表，不删除业务数据，不伪造过去的明细。
USE `date-project`;
CREATE TABLE IF NOT EXISTS ebay_inventory_detail_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  snapshot_id BIGINT UNSIGNED NOT NULL COMMENT '共享日期批次；主表stat_date唯一',
  site VARCHAR(32) NOT NULL,
  sku VARCHAR(255) NOT NULL,
  item_json JSON NOT NULL COMMENT '当时完整字段、异常提示及Decimal类型标记，不关联最新来源重算',
  PRIMARY KEY (id),
  UNIQUE KEY uk_inventory_history_sku (snapshot_id,site,sku),
  CONSTRAINT fk_inventory_detail_history_snapshot FOREIGN KEY (snapshot_id)
    REFERENCES ebay_inventory_pivot_snapshot(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Ebay库存明细历史：同日事务覆盖，跨日长期保存，与负责人透视同批';
