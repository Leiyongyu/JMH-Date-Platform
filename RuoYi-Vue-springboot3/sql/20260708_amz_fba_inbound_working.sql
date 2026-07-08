-- AMZ补货新增FBA计划入库字段，并用其替代待出库参与补货抵扣。
ALTER TABLE amz_product_performance_inventory
  ADD COLUMN fba_inbound_working INT NOT NULL DEFAULT 0 COMMENT 'FBA计划入库' AFTER fba_inbound;

ALTER TABLE amz_replenishment_snapshot
  ADD COLUMN fba_inbound_working INT NULL DEFAULT 0 COMMENT 'FBA计划入库' AFTER fba_inbound;

ALTER TABLE amz_replenishment_formula_config
  ADD COLUMN deduct_fba_inbound_working TINYINT(1) NOT NULL DEFAULT 0 COMMENT '扣减FBA计划入库' AFTER deduct_fba_inbound;

UPDATE amz_replenishment_formula_config
SET deduct_pending_ship_qty = 0,
    deduct_fba_inbound_working = 1,
    formula_replenish = REPLACE(formula_replenish, '{locked}', '{inboundWorking}'),
    formula_restock = REPLACE(formula_restock, '{locked}', '{inboundWorking}')
WHERE region_group = 'EU';
