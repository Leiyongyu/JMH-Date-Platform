"""报关商品数据访问，复用 Date-Project 连接池并读写 jmh_data_platform.products。"""

from __future__ import annotations

import re
from typing import Any

from backend.customs_declaration.config import PRODUCTS_DATABASE
from backend.database import db_connection


if not re.fullmatch(r"[0-9A-Za-z_]+", PRODUCTS_DATABASE):
    raise RuntimeError("SHOP_SOURCE_DATABASE 只能包含字母、数字和下划线")

PRODUCTS_TABLE = f"`{PRODUCTS_DATABASE}`.`products`"
EDITABLE_FIELDS = frozenset(
    {
        "hs_code",
        "hs_description",
        "description_cn",
        "model",
        "unit_price_usd",
        "currency",
        "origin_country",
        "destination_country",
        "source_location",
        "exemption",
    }
)


def init_database() -> None:
    """只确保配置库中的 products 表存在，不创建数据库或切换账号。"""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {PRODUCTS_TABLE} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sku VARCHAR(100) UNIQUE NOT NULL COMMENT 'SKU编码',
                    description_cn VARCHAR(255) DEFAULT NULL COMMENT '中文品名',
                    model VARCHAR(255) NOT NULL DEFAULT '' COMMENT '规格型号',
                    unit VARCHAR(50) NOT NULL DEFAULT '' COMMENT '单位',
                    unit_price_usd DECIMAL(18,4) DEFAULT NULL COMMENT 'USD单价',
                    currency VARCHAR(20) NOT NULL DEFAULT 'USD' COMMENT '币制',
                    single_weight DECIMAL(18,6) DEFAULT NULL COMMENT '单个重量(kg)',
                    hs_code VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'HS编码',
                    hs_description TEXT DEFAULT NULL COMMENT '申报要素',
                    origin_country VARCHAR(100) NOT NULL DEFAULT '中国',
                    destination_country VARCHAR(100) NOT NULL DEFAULT '',
                    source_location VARCHAR(255) NOT NULL DEFAULT '',
                    exemption VARCHAR(100) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        connection.commit()


def get_all_products() -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {PRODUCTS_TABLE} ORDER BY id")
            return list(cursor.fetchall())


def get_product_by_sku(sku: str) -> dict[str, Any] | None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {PRODUCTS_TABLE} WHERE sku = %s",
                (sku,),
            )
            return cursor.fetchone()


def search_products(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 100))
    like = f"%{keyword}%"
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM {PRODUCTS_TABLE}
                WHERE sku LIKE %s OR description_cn LIKE %s
                ORDER BY CASE WHEN sku LIKE %s THEN 0 ELSE 1 END, sku
                LIMIT %s
                """,
                (like, like, like, safe_limit),
            )
            return list(cursor.fetchall())


def upsert_product(data: dict[str, Any]) -> None:
    sql = f"""
        INSERT INTO {PRODUCTS_TABLE}
        (sku, description_cn, model, unit, unit_price_usd, currency,
         single_weight, hs_code, hs_description, origin_country,
         destination_country, source_location, exemption)
        VALUES
        (%(sku)s, %(description_cn)s, %(model)s, %(unit)s,
         %(unit_price_usd)s, %(currency)s, %(single_weight)s,
         %(hs_code)s, %(hs_description)s, %(origin_country)s,
         %(destination_country)s, %(source_location)s, %(exemption)s)
        ON DUPLICATE KEY UPDATE
            description_cn = VALUES(description_cn),
            model = VALUES(model),
            unit = VALUES(unit),
            unit_price_usd = VALUES(unit_price_usd),
            currency = VALUES(currency),
            single_weight = VALUES(single_weight),
            hs_code = VALUES(hs_code),
            hs_description = VALUES(hs_description),
            origin_country = VALUES(origin_country),
            destination_country = VALUES(destination_country),
            source_location = VALUES(source_location),
            exemption = VALUES(exemption)
    """
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, data)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def update_product_field(sku: str, field: str, value: Any) -> None:
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"不允许更新字段: {field}")
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {PRODUCTS_TABLE} "
                    f"SET `{field}` = %s, updated_at = NOW() WHERE sku = %s",
                    (value, sku),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
