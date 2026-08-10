-- 修复 Amazon 不适配、货描不符原因枚举及明确多语言备注的历史分类。
-- 可重复执行；不修改 ODS 原始数据，DWS 只标记为待后端按现有快照重算。

START TRANSACTION;

-- Amazon 明确原因枚举优先于 AI：五类归产品不适配，NOT_AS_DESCRIBED 归 listing货描不符。
UPDATE dwd_amz_sop_after_sales
SET after_reason_zh = CASE LOWER(TRIM(COALESCE(after_reason,'')))
        WHEN 'not_compatible' THEN '商品不适配'
        WHEN 'incompatible' THEN '商品不适配'
        WHEN 'part_not_compatible' THEN '零件不适配'
        WHEN 'poor_fit' THEN '尺寸或安装不适配'
        WHEN 'apparel_too_small' THEN '尺寸过小'
        WHEN 'apparel_too_large' THEN '尺寸过大'
        WHEN 'not_as_described' THEN '商品与描述不符'
        ELSE after_reason_zh
    END,
    return_status_zh = CASE
        WHEN LOWER(TRIM(COALESCE(return_status,''))) = 'unit returned to inventory'
            THEN '退货已退回库存'
        ELSE return_status_zh
    END,
    buyers_note_zh = CASE
        WHEN LOWER(TRIM(COALESCE(buyers_note,''))) IN ('passt nicht','nicht passend')
            THEN '不适配'
        ELSE buyers_note_zh
    END,
    big_category = '不适配',
    small_category = CASE
        WHEN LOWER(TRIM(COALESCE(after_reason,''))) = 'not_as_described'
            THEN 'listing货描不符'
        ELSE '产品不适配'
    END,
    classify_method = 'rule',
    confidence = 0.980000,
    update_time = NOW()
WHERE LOWER(TRIM(COALESCE(after_reason,''))) IN (
    'not_compatible','incompatible','part_not_compatible','poor_fit',
    'apparel_too_small','apparel_too_large','not_as_described'
);

-- “其他”中的明确货描不符备注，优先于通用的不适配措辞。
UPDATE dwd_amz_sop_after_sales
SET big_category = '不适配', small_category = 'listing货描不符',
    classify_method = 'rule', confidence = 0.850000, update_time = NOW()
WHERE big_category = '其他'
  AND LOWER(COALESCE(buyers_note,'')) REGEXP
      'not as described|description doesn.?t match|description inaccurate|inaccurate description|beschreibung falsch|nicht wie beschrieben|different from pic|descrizione.*non accurata';

-- “其他”中的明确多语言不适配/尺寸不符备注。
UPDATE dwd_amz_sop_after_sales
SET big_category = '不适配', small_category = '产品不适配',
    classify_method = 'rule', confidence = 0.850000, update_time = NOW()
WHERE big_category = '其他'
  AND LOWER(COALESCE(buyers_note,'')) REGEXP
      'not compatible|not fit|doesn.?t fit|poor fit|incorrect size|too small|too large|passt nicht|nicht passend|nicht kompatibel|non compatibile|non è compatibile|pas compatible|n.est pas compatible|no es compatible|no compatible|incompatibilidad';

UPDATE dim_amz_sop_classification_cache
SET after_reason_zh = CASE LOWER(TRIM(COALESCE(after_reason,'')))
        WHEN 'not_compatible' THEN '商品不适配'
        WHEN 'incompatible' THEN '商品不适配'
        WHEN 'part_not_compatible' THEN '零件不适配'
        WHEN 'poor_fit' THEN '尺寸或安装不适配'
        WHEN 'apparel_too_small' THEN '尺寸过小'
        WHEN 'apparel_too_large' THEN '尺寸过大'
        WHEN 'not_as_described' THEN '商品与描述不符'
        ELSE after_reason_zh
    END,
    big_category = '不适配',
    small_category = CASE
        WHEN LOWER(TRIM(COALESCE(after_reason,''))) = 'not_as_described'
            THEN 'listing货描不符'
        ELSE '产品不适配'
    END,
    classify_method = 'rule', confidence = 0.980000,
    evidence = 'Amazon退货原因枚举确定性规则V3', update_time = NOW()
WHERE LOWER(TRIM(COALESCE(after_reason,''))) IN (
    'not_compatible','incompatible','part_not_compatible','poor_fit',
    'apparel_too_small','apparel_too_large','not_as_described'
);

UPDATE dws_amz_sop_after_sales_summary
SET sync_batch_id = 'STALE-MISMATCH-RULE-V3', update_time = NOW();

COMMIT;
