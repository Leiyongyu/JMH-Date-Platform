-- 领星产品表现库存字段，只保留 AMZ 补货需要的库存口径字段。
CREATE TABLE IF NOT EXISTS amz_product_performance_inventory (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  sid INT NOT NULL COMMENT '店铺ID',
  seller_sku VARCHAR(128) NOT NULL COMMENT 'Seller SKU/MSKU',
  local_sku VARCHAR(128) DEFAULT NULL COMMENT '本地SKU',
  fba_fulfillable INT NOT NULL DEFAULT 0 COMMENT 'FBA可售',
  fba_transfer INT NOT NULL DEFAULT 0 COMMENT 'FBA待调仓',
  fba_receiving INT NOT NULL DEFAULT 0 COMMENT 'FBA入库中',
  fba_reserved INT NOT NULL DEFAULT 0 COMMENT 'FBA预留：待发货+调仓中',
  fba_inbound INT NOT NULL DEFAULT 0 COMMENT 'FBA在途',
  fba_inbound_working INT NOT NULL DEFAULT 0 COMMENT 'FBA计划入库',
  fba_stock INT NOT NULL DEFAULT 0 COMMENT 'FBA在库：可售+待调仓+入库中+预留',
  sync_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_sid_seller_sku (sid, seller_sku),
  KEY idx_seller_sku (seller_sku),
  KEY idx_sid (sid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='领星Amazon产品表现库存';

-- 可选：在若依定时任务中预置每天执行的同步任务。status=1 表示暂停，确认时间后在页面启用。
INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT
  '领星-Amazon产品表现库存',
  'OPERATION',
  'operationSyncTask.syncAmzProductPerformanceInventory',
  '0 20 2 * * ?',
  '1',
  '1',
  '1',
  'system',
  SYSDATE(),
  '每天拉取产品表现接口中的FBA库存口径；FBA在库=可售+待调仓+入库中+预留'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target = 'operationSyncTask.syncAmzProductPerformanceInventory'
);
