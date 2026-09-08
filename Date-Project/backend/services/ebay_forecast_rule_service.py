"""Editing and draft preview of the existing v2 forecast rules (no data sync)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, DecimalException
from typing import Any

from pymysql.err import ProgrammingError

from backend.repositories import ebay_replenishment_v2_repository as repository
from backend.services import ebay_forecast_rule_engine as engine
from backend.services import ebay_replenishment_v2_service as replenishment


def _check_rules(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(rows) != 13:
        raise ValueError("必须提交完整13条规则，不能新增或删除")
    normalized = []
    checks = []
    seen = set()
    for row in rows:
        no = row.get("rule_no")
        if type(no) is not int or no not in range(1, 14) or no in seen:
            raise ValueError("规则序号必须且只能为1至13，不能重复")
        seen.add(no)
        nature = str(row.get("product_nature") or "").strip()
        if nature != ("新品" if no == 1 else "老品"):
            raise ValueError(f"规则{no}的产品性质不可修改")
        status = row.get("status")
        if type(status) is not int or status not in (0, 1):
            raise ValueError(f"规则{no}的启用状态必须为0或1")
        remark = str(row.get("remark") or "").strip()
        if len(remark) > 255:
            raise ValueError(f"规则{no}的说明不能超过255字符")
        item = dict(rule_no=no, product_nature=nature, status=status, remark=remark or None)
        errors = {}
        for field, kind in (("condition_expr", "bool"), ("formula_expr", "number")):
            expression = str(row.get(field) or "").strip()
            item[field] = expression
            try:
                engine.parse_expression(expression, kind)
            except (ValueError, SyntaxError, DecimalException, RecursionError) as exc:
                errors[field] = str(exc)
        normalized.append(item)
        checks.append({"rule_no": no, "valid": not errors, "errors": errors})
    return sorted(normalized, key=lambda item: item["rule_no"]), {
        "valid": all(row["valid"] for row in checks),
        "rows": sorted(checks, key=lambda item: item["rule_no"]),
    }


def validate_forecast_rules(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """No database writes, and validate disabled expressions too."""
    return _check_rules(rows)[1]


def list_forecast_rules() -> dict[str, Any]:
    try:
        rows = repository.list_forecast_rule_rows()
    except ProgrammingError as exc:
        if exc.args and exc.args[0] == 1146:
            raise ValueError("规则表未部署，请先执行20260908预估销量2规则部署脚本") from exc
        raise
    if len(rows) != 13 or {int(row["rule_no"]) for row in rows} != set(range(1, 14)):
        raise ValueError("规则表必须包含完整13条初始化规则，请先检查部署")
    return {"configs": rows, "revision": repository.forecast_rules_revision(rows)}


def save_forecast_rules(
    rows: list[dict[str, Any]], revision: str, operator: str | None = None,
) -> dict[str, Any]:
    normalized, checks = _check_rules(rows)
    if not checks["valid"]:
        invalid = next(row for row in checks["rows"] if not row["valid"])
        raise ValueError(f"规则{invalid['rule_no']}校验失败：" + "；".join(invalid["errors"].values()))
    if not revision or len(revision) != 64:
        raise ValueError("缺少规则版本，请重新打开编辑器")
    repository.save_forecast_rules(normalized, str(operator or "SYSTEM").strip()[:64] or "SYSTEM", revision)
    return list_forecast_rules()


def preview_forecast(
    rows: list[dict[str, Any]], *, product_nature: str | None,
    sales_7d: Decimal, sales_15d: Decimal, sales_30d: Decimal, age_days: Decimal | None,
) -> dict[str, Any]:
    # Crucially preview the unsaved draft, not the persisted table.
    normalized, checks = _check_rules(rows)
    if not checks["valid"]:
        return {"validation": checks, "result": {
            "status": "invalid_draft", "matched_rule_no": None, "value": None,
            "message": "草稿规则未通过语法校验，请先修正标红的规则",
        }}
    prepared = engine.prepare_rules([row for row in normalized if row["status"] == 1])
    trace: dict[str, Any] = {}
    engine.calculate_forecast(product_nature=product_nature,
        sales_7d=sales_7d, sales_15d=sales_15d, sales_30d=sales_30d,
        age_days=age_days, rules=prepared, trace=trace)
    matched = next((row for row in normalized if row["rule_no"] == trace.get("matched_rule_no")), None)
    trace["remark"] = matched["remark"] if matched else None
    return {"validation": checks, "result": trace}


def forecast_sku_inputs(site: str, sku: str) -> dict[str, Any]:
    site, sku = site.strip(), sku.strip()
    if not site or not sku or len(site) > 100 or len(sku) > 255:
        raise ValueError("请填写有效站点和完整SKU")
    row = repository.forecast_sku_sales(site, sku)
    if row is None:
        raise ValueError("没有精确匹配此站点和完整SKU的订单数据")
    # Use canonical values returned by the source, not a fuzzy first result.
    site, sku = row["site"], row["sku"]
    age = repository.overseas_inventory_age_by_sku().get((site, sku))
    nature = replenishment._product_nature(
        repository.first_listing_date_by_sku().get((sku, site)), date.today())
    return {
        "site": site, "sku": sku, "product_nature": nature,
        "sales_7d": format(Decimal(str(row["sales_7d"])), "f"),
        "sales_15d": format(Decimal(str(row["sales_15d"])), "f"),
        "sales_30d": format(Decimal(str(row["sales_30d"])), "f"),
        "age_days": format(age, "f") if age is not None else None,
        "anchor_date": row["anchor_date"],
    }
