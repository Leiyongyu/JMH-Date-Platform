-- ============================================================
-- shop_list 索引修正：用 (platform_code, store_id) 联合唯一键
-- 可重复执行
-- ============================================================

-- 删旧唯一索引
DROP INDEX IF EXISTS uk_store_id ON shop_list;

-- 建新的联合唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS uk_platform_store ON shop_list (platform_code, store_id);
