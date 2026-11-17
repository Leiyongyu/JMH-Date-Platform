-- 报关 SKU 括号规则：
-- 1. 库存匹配只使用括号前的仓库 SKU，再执行原有去品牌前缀规则。
-- 2. 括号内容只用于 Java 生成报关文件，不替换数据库 SKU。
-- 3. 同时支持半角 ()、全角 （） 及括号前的换行/空格。

USE `jmh_data_platform`;
SET NAMES utf8mb4;

DROP FUNCTION IF EXISTS `normalize_customs_sku_key`;
DELIMITER $$
CREATE FUNCTION `normalize_customs_sku_key`(p_sku VARCHAR(512)) RETURNS varchar(512) CHARSET utf8mb4
    NO SQL
    DETERMINISTIC
BEGIN
    DECLARE normalized_sku VARCHAR(512);
    DECLARE prefix VARCHAR(255);
    DECLARE dash_pos INT;
    DECLARE half_parenthesis_pos INT;
    DECLARE full_parenthesis_pos INT;
    DECLARE parenthesis_pos INT DEFAULT 0;
    DECLARE segment VARCHAR(255);
    DECLARE rest VARCHAR(512);

    IF p_sku IS NULL OR REGEXP_REPLACE(p_sku, '^[[:space:]]+|[[:space:]]+$', '') = '' THEN
        RETURN '';
    END IF;

    SET normalized_sku = REGEXP_REPLACE(p_sku, '^[[:space:]]+|[[:space:]]+$', '');
    SET half_parenthesis_pos = INSTR(normalized_sku, '(');
    SET full_parenthesis_pos = INSTR(normalized_sku, '（');
    IF half_parenthesis_pos > 0 AND full_parenthesis_pos > 0 THEN
        SET parenthesis_pos = LEAST(half_parenthesis_pos, full_parenthesis_pos);
    ELSEIF half_parenthesis_pos > 0 THEN
        SET parenthesis_pos = half_parenthesis_pos;
    ELSEIF full_parenthesis_pos > 0 THEN
        SET parenthesis_pos = full_parenthesis_pos;
    END IF;
    IF parenthesis_pos > 1 THEN
        SET normalized_sku = REGEXP_REPLACE(
            LEFT(normalized_sku, parenthesis_pos - 1),
            '^[[:space:]]+|[[:space:]]+$',
            ''
        );
    END IF;

    SET dash_pos = INSTR(normalized_sku, '-');
    IF dash_pos = 0 THEN
        RETURN normalized_sku;
    END IF;

    SET prefix = UPPER(SUBSTRING_INDEX(normalized_sku, '-', 1));
    IF prefix LIKE '%PC%' THEN
        RETURN normalized_sku;
    END IF;

    SET rest = normalized_sku;
    segment_loop: LOOP
        SET dash_pos = INSTR(rest, '-');
        IF dash_pos = 0 THEN
            SET segment = rest;
        ELSE
            SET segment = LEFT(rest, dash_pos - 1);
        END IF;

        IF segment REGEXP '[0-9]' THEN
            RETURN CONCAT(
                REGEXP_REPLACE(segment, '^[^0-9]+', ''),
                IF(dash_pos = 0, '', SUBSTRING(rest, dash_pos))
            );
        END IF;

        IF dash_pos = 0 THEN
            LEAVE segment_loop;
        END IF;
        SET rest = SUBSTRING(rest, dash_pos + 1);
    END LOOP segment_loop;

    RETURN normalized_sku;
END$$
DELIMITER ;

-- 历史表保存的 sku_key 不会随函数自动变化，因此做幂等回填。
UPDATE `customs_declaration_history`
SET `sku_key` = normalize_customs_sku_key(`sku`)
WHERE `sku_key` <> normalize_customs_sku_key(`sku`);
