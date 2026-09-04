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


def first_listing_date_by_sku() -> dict[tuple[str, str], Any]:
    """按完整 MSKU 和站点精确读取最早刊登时间；没有记录的 SKU 不返回。"""

    database = _source_database()
    query = f"""
        SELECT msku,site_name,MIN(listing_start_time) first_listing_start_time
        FROM `{database}`.ebay_product_listing
        WHERE msku IS NOT NULL AND TRIM(msku)<>''
          AND site_name IS NOT NULL AND TRIM(site_name)<>''
          AND listing_start_time IS NOT NULL
        GROUP BY msku,site_name
    """
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query)
        return {
            (_text(row.get("msku")), _text(row.get("site_name"))): row.get(
                "first_listing_start_time"
            )
            for row in cursor.fetchall()
            if _text(row.get("msku")) and _text(row.get("site_name"))
        }


def overseas_inventory_age_by_sku() -> dict[tuple[str, str], Decimal]:
    """按站点和SKU读取最新海外仓快照中最老批次的库龄。

    谷仓库存库龄接口按批次返回明细。这里取最老批次而非库存量加权平均：
    规则1需要表达SKU在该站点有货可卖了多久，新到货的大批次不应降低库龄。
    """

    query = """
        SELECT CASE WHEN warehouse_code IN ('DE','CZ','IT') THEN '德国'
                    WHEN warehouse_code='UK' THEN '英国'
                    WHEN warehouse_code='FR' THEN '法国'
                    WHEN warehouse_code LIKE 'US%%' THEN '美国' END site,
               sku,
               MAX(warehouse_age_days) age_days
        FROM dwd_ebay_inventory_age_cost_snapshot
        WHERE pull_month=(
                  SELECT MAX(pull_month)
                  FROM dwd_ebay_inventory_age_cost_snapshot
              )
          AND match_status='MATCHED'
          AND sku IS NOT NULL AND TRIM(sku)<>''
        GROUP BY 1,2
        HAVING site IS NOT NULL AND age_days IS NOT NULL
    """
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query)
        return {
            (_text(row.get("site")), _text(row.get("sku"))): _decimal(
                row.get("age_days")
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


def forecast_formula_by_group() -> dict[str, Any]:
    """读取启用的预估销量2配置；不提供任何代码默认值。"""

    grouped: dict[str, Any] = {"OLD_7D": [], "OLD_15D": []}
    for row in list_forecast_formula_rows(active_only=True):
        group = row["rule_group"]
        if group == "MISC":
            grouped["MISC"] = row
        elif group in {"OLD_7D", "OLD_15D"}:
            grouped[group].append(row)
    return grouped


def list_forecast_formula_rows(
    active_only: bool = False,
) -> list[dict[str, Any]]:
    database = _source_database()
    where_sql = "WHERE status=1" if active_only else ""
    query = f"""
        SELECT rule_group,tier,threshold_ratio,weight_7d,weight_15d,
               weight_30d,month_days,new_age_cap,old_fallback_ratio,
               remark,status,update_by,update_time
        FROM `{database}`.ebay_replenishment_v2_forecast_formula
        {where_sql}
        ORDER BY FIELD(rule_group,'OLD_7D','OLD_15D','MISC'),tier
    """
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    decimal_fields = (
        "threshold_ratio",
        "weight_7d",
        "weight_15d",
        "weight_30d",
        "month_days",
        "new_age_cap",
        "old_fallback_ratio",
    )
    return [
        {
            **row,
            "rule_group": _text(row.get("rule_group")).upper(),
            "tier": int(row.get("tier") or 0),
            **{
                field: _nullable_decimal(row.get(field))
                for field in decimal_fields
            },
        }
        for row in rows
        if _text(row.get("rule_group")) and int(row.get("tier") or 0) > 0
    ]


def save_forecast_formula_rows(
    rows: list[dict[str, Any]], operator: str
) -> None:
    """在一个事务内覆盖预估销量2的全部启用配置。"""

    database = _source_database()
    deactivate_query = f"""
        UPDATE `{database}`.ebay_replenishment_v2_forecast_formula
        SET status=0,update_by=%s,update_time=NOW()
        WHERE status<>0
    """
    upsert_query = f"""
        INSERT INTO `{database}`.ebay_replenishment_v2_forecast_formula
          (rule_group,tier,threshold_ratio,weight_7d,weight_15d,weight_30d,
           month_days,new_age_cap,old_fallback_ratio,status,remark,update_by,
           update_time)
        VALUES
          (%(rule_group)s,%(tier)s,%(threshold_ratio)s,%(weight_7d)s,
           %(weight_15d)s,%(weight_30d)s,%(month_days)s,%(new_age_cap)s,
           %(old_fallback_ratio)s,1,%(remark)s,%(operator)s,NOW())
        ON DUPLICATE KEY UPDATE
          threshold_ratio=VALUES(threshold_ratio),weight_7d=VALUES(weight_7d),
          weight_15d=VALUES(weight_15d),weight_30d=VALUES(weight_30d),
          month_days=VALUES(month_days),new_age_cap=VALUES(new_age_cap),
          old_fallback_ratio=VALUES(old_fallback_ratio),status=1,
          remark=VALUES(remark),update_by=VALUES(update_by),update_time=NOW()
    """
    params = [{**row, "operator": operator} for row in rows]
    with db_connection() as connection, connection.cursor() as cursor:
        try:
            cursor.execute(deactivate_query, (operator,))
            cursor.executemany(upsert_query, params)
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


def _nullable_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))
