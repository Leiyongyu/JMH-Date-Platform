from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.config import settings
from backend.database import db_connection


def lead_time_days_by_sku() -> dict[tuple[str, str], Decimal]:
    """按站点和完整 SKU 一次读取总提前天数；没有配置的 SKU 不返回。"""

    database = _source_database()
    query = f"""
        SELECT site,sku,
               COALESCE(chengdu_warehouse_to_warehouse_days,0)
             + COALESCE(chengdu_qc_outbound_days,0)
             + COALESCE(overseas_transit_to_listing_days,0) total_days
        FROM `{database}`.ebay_replenishment_v2_lead_time
    """
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query)
        return {
            (_text(row.get("site")), _text(row.get("sku"))): _decimal(
                row.get("total_days")
            )
            for row in cursor.fetchall()
            if _text(row.get("site")) and _text(row.get("sku"))
        }


def formula_by_level() -> dict[str, dict[str, Decimal]]:
    """读取启用的 v2 系数；缺失级别不会生成任何代码默认值。"""

    return {
        row["product_level"]: {
            "safety_coefficient": row["safety_coefficient"],
            "suggest_coefficient": row["suggest_coefficient"],
        }
        for row in list_formula_rows(active_only=True)
    }


def list_formula_rows(active_only: bool = False) -> list[dict[str, Any]]:
    database = _source_database()
    where_sql = "WHERE status=1" if active_only else ""
    query = f"""
        SELECT product_level,safety_coefficient,suggest_coefficient,
               remark,status,update_by,update_time
        FROM `{database}`.ebay_replenishment_v2_formula
        {where_sql}
        ORDER BY FIELD(product_level,'S','A','B','C'),product_level
    """
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    return [
        {
            **row,
            "product_level": _text(row.get("product_level")).upper(),
            "safety_coefficient": _decimal(row.get("safety_coefficient")),
            "suggest_coefficient": _decimal(row.get("suggest_coefficient")),
        }
        for row in rows
        if _text(row.get("product_level"))
    ]


def save_formula_rows(rows: list[dict[str, Any]], operator: str) -> None:
    """在一个事务内按产品级别覆盖四行系数。"""

    database = _source_database()
    query = f"""
        INSERT INTO `{database}`.ebay_replenishment_v2_formula
          (product_level,safety_coefficient,suggest_coefficient,remark,status,
           update_by,create_time,update_time)
        VALUES
          (%(product_level)s,%(safety_coefficient)s,%(suggest_coefficient)s,
           %(remark)s,1,%(operator)s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
          safety_coefficient=VALUES(safety_coefficient),
          suggest_coefficient=VALUES(suggest_coefficient),
          remark=VALUES(remark),status=1,update_by=VALUES(update_by),
          update_time=NOW()
    """
    params = [{**row, "operator": operator} for row in rows]
    with db_connection() as connection, connection.cursor() as cursor:
        try:
            cursor.executemany(query, params)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _source_database() -> str:
    return (settings.shop_source_database.strip() or "jmh_data_platform").replace(
        "`", "``"
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))
