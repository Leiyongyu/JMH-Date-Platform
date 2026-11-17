-- Python数据库；产品等级改为按"历史最大月销 + 利润率"实时计算，
-- 上传等级表的接口、前端入口与解析代码已一并移除，此表不再有任何读写方。
-- 表内只有人工上传的等级文本，没有其他模块引用，删除后不影响历史快照：
-- dws层的库存明细历史行在生成当天已把等级值写进快照JSON，不回查本表。
USE `date-project`;
SET NAMES utf8mb4;

DROP TABLE IF EXISTS ebay_inventory_detail_grade;
