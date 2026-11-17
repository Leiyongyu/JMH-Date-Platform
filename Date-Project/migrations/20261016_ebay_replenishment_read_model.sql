-- 在 Python 应用库执行。仅新增补货2.0派生表，不改变订单、库存、人工备注或历史报表。
CREATE TABLE IF NOT EXISTS dws_ebay_replenishment_daily (
  sales_date DATE NOT NULL,
  site VARCHAR(100) NOT NULL,
  sku VARCHAR(255) NOT NULL,
  sales_qty DECIMAL(30,6) NOT NULL,
  gross_profit_amount DECIMAL(30,6) NOT NULL,
  paid_amount DECIMAL(30,6) NOT NULL,
  return_qty DECIMAL(30,6) NOT NULL,
  return_amount DECIMAL(30,6) NOT NULL,
  quality_return_qty DECIMAL(30,6) NOT NULL,
  unclassified_return_qty DECIMAL(30,6) NOT NULL,
  latest_payment_time DATETIME(6) NOT NULL,
  latest_order_id BIGINT NOT NULL,
  product_name TEXT NULL,
  PRIMARY KEY (sales_date,site,sku),
  KEY idx_replenishment_daily_product (site,sku,sales_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dws_ebay_replenishment_generation (
  generation CHAR(32) NOT NULL PRIMARY KEY,
  reference_date DATE NOT NULL,
  source_signature CHAR(64) NOT NULL,
  engine_version VARCHAR(30) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  metadata JSON NOT NULL,
  KEY idx_replenishment_generation_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dws_ebay_replenishment_result (
  generation CHAR(32) NOT NULL,
  site VARCHAR(100) NOT NULL,
  sku VARCHAR(255) NOT NULL,
  product_name TEXT NULL,
  product_level VARCHAR(20) NULL,
  product_nature VARCHAR(20) NULL,
  sales_qty_7d DECIMAL(30,6) NULL,
  sales_qty_15d DECIMAL(30,6) NULL,
  sales_qty_30d DECIMAL(30,6) NULL,
  sales_qty DECIMAL(30,6) NULL,
  gross_profit_amount DECIMAL(30,6) NULL,
  profit_rate DECIMAL(30,12) NULL,
  return_qty DECIMAL(30,6) NULL,
  return_rate DECIMAL(30,12) NULL,
  return_amount DECIMAL(30,6) NULL,
  forecast_sales_quantity_2 DECIMAL(30,6) NULL,
  safety_stock_quantity DECIMAL(30,6) NULL,
  suggested_replenishment_quantity DECIMAL(30,6) NULL,
  safety_stock_quantity_2 DECIMAL(30,6) NULL,
  suggested_replenishment_quantity_2 DECIMAL(30,6) NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (generation,site,sku),
  KEY idx_replenishment_result_grade (generation,product_level),
  KEY idx_replenishment_result_sales (generation,sales_qty_30d),
  KEY idx_replenishment_result_safety (generation,safety_stock_quantity),
  KEY idx_replenishment_result_suggest (generation,suggested_replenishment_quantity),
  KEY idx_replenishment_result_safety2 (generation,safety_stock_quantity_2),
  KEY idx_replenishment_result_suggest2 (generation,suggested_replenishment_quantity_2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dws_ebay_replenishment_state (
  state_id TINYINT NOT NULL PRIMARY KEY,
  active_generation CHAR(32) NULL,
  daily_signature CHAR(64) NULL,
  checked_at DATETIME(6) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT IGNORE INTO dws_ebay_replenishment_state(state_id) VALUES(1);
