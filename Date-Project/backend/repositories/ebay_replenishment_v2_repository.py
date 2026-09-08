from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any

from pymysql.err import ProgrammingError

from backend.config import settings
from backend.database import db_connection

logger = logging.getLogger(__name__)

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
        GROUP BY site_name,msku
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


def forecast_rules() -> list[dict[str, Any]]:
    """读取启用规则，不为空表达式提供默认值；错误交由解释器显式处理。

    表属于jmh_data_platform（源库），旧forecast_formula表保留但不再读写。
    """
    database = _source_database()
    query = f"""
        SELECT rule_no,product_nature,condition_expr,formula_expr
        FROM `{database}`.ebay_replenishment_v2_forecast_rule
        WHERE status=1
        ORDER BY rule_no
    """
    try:
        with db_connection() as connection, connection.cursor() as cursor:
            cursor.execute(query)
            return list(cursor.fetchall())
    except ProgrammingError as exc:
        if not exc.args or exc.args[0] != 1146:
            raise
        logger.error("预估销量2规则表未部署：%s.ebay_replenishment_v2_forecast_rule；该列显示--", database)
        return []


def list_forecast_rule_rows() -> list[dict[str, Any]]:
    """Editor reads disabled rules too; missing table must be an actionable error."""
    database = _source_database()
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT rule_no,product_nature,condition_expr,formula_expr,remark,status,
                   update_by,update_time
            FROM `{database}`.ebay_replenishment_v2_forecast_rule
            ORDER BY rule_no
        """)
        return list(cursor.fetchall())


def forecast_rules_revision(rows: list[dict[str, Any]]) -> str:
    fields = ("rule_no", "product_nature", "condition_expr", "formula_expr", "remark", "status")
    normalized = [{key: (row.get(key) if key in {"rule_no", "status"} else row.get(key) or "")
                   for key in fields} for row in sorted(rows, key=lambda row: row["rule_no"])]
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def save_forecast_rules(rows: list[dict[str, Any]], operator: str, revision: str) -> None:
    """Only update initialized rules, atomically; reject stale editor sessions."""
    database = _source_database()
    with db_connection() as connection, connection.cursor() as cursor:
        try:
            cursor.execute(f"""
                SELECT rule_no,product_nature,condition_expr,formula_expr,remark,status
                FROM `{database}`.ebay_replenishment_v2_forecast_rule
                ORDER BY rule_no FOR UPDATE
            """)
            current = list(cursor.fetchall())
            if {int(row["rule_no"]) for row in current} != set(range(1, 14)):
                raise ValueError("规则表必须已初始化完整13条规则，请先检查部署脚本")
            if forecast_rules_revision(current) != revision:
                raise ValueError("规则已被其他人修改，请重新打开编辑器后再保存")
            cursor.executemany(f"""
                UPDATE `{database}`.ebay_replenishment_v2_forecast_rule
                SET condition_expr=%(condition_expr)s,formula_expr=%(formula_expr)s,
                    remark=%(remark)s,status=%(status)s,update_by=%(operator)s,update_time=NOW()
                WHERE rule_no=%(rule_no)s
            """, [{**row, "operator": operator} for row in rows])
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def forecast_sku_sales(site: str, sku: str) -> dict[str, Any] | None:
    """Exact site/full-SKU lookup; anchor is global, identical to the list."""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("""
            WITH anchor AS (
                SELECT COALESCE(DATE(MAX(payment_time)),CURDATE()) anchor_date
                FROM dwd_ebay_sku_analysis_order
            )
            SELECT recent.site_name site,recent.inventory_sku sku,anchor.anchor_date,
                   COALESCE(SUM(CASE WHEN recent.payment_time >= DATE_SUB(anchor.anchor_date,INTERVAL 6 DAY)
                                     AND recent.payment_time < DATE_ADD(anchor.anchor_date,INTERVAL 1 DAY)
                                     THEN recent.purchase_quantity ELSE 0 END),0) sales_7d,
                   COALESCE(SUM(CASE WHEN recent.payment_time >= DATE_SUB(anchor.anchor_date,INTERVAL 14 DAY)
                                     AND recent.payment_time < DATE_ADD(anchor.anchor_date,INTERVAL 1 DAY)
                                     THEN recent.purchase_quantity ELSE 0 END),0) sales_15d,
                   COALESCE(SUM(CASE WHEN recent.payment_time >= DATE_SUB(anchor.anchor_date,INTERVAL 29 DAY)
                                     AND recent.payment_time < DATE_ADD(anchor.anchor_date,INTERVAL 1 DAY)
                                     THEN recent.purchase_quantity ELSE 0 END),0) sales_30d
            FROM dwd_ebay_sku_analysis_order recent CROSS JOIN anchor
            WHERE recent.site_name=%s AND recent.inventory_sku=%s
            GROUP BY recent.site_name,recent.inventory_sku,anchor.anchor_date
        """, (site, sku))
        return cursor.fetchone()


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
