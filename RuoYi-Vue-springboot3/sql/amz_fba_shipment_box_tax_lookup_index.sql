-- FBA货件展开SKU及含税状态匹配优化索引
ALTER TABLE amz_fba_shipment_box
  ADD INDEX idx_fba_box_shipment_sku (shipment_id, sku);

-- FBA装箱信息同步后按本次货件回填本地SKU/商品名
ALTER TABLE amz_fba_shipment_box
  ADD INDEX idx_fba_box_shipment_msku (shipment_id, msku);

ALTER TABLE amz_product_listing
  ADD INDEX idx_amz_listing_sid_seller_sku (sid, seller_sku);
