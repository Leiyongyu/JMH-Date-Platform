"""Editable product grades; isolated variable whitelist, fail closed, request-local parsing."""
from __future__ import annotations

import ast
import logging
from decimal import Decimal, DecimalException
from dataclasses import dataclass, field
from pymysql.err import ProgrammingError
from backend.services import ebay_forecast_rule_engine as engine
from backend.repositories import ebay_replenishment_v2_repository as repository

LOG = logging.getLogger(__name__)
VARIABLES = frozenset({"return_rate", "profit_rate", "sell_through_ratio"})
LEVELS = frozenset({"S", "A", "B", "C"})


@dataclass
class PreparedLevels:
    rules: list = field(default_factory=list)
    reported: set = field(default_factory=set)
    invalid: bool = False


def prepare_levels(rows):
    prepared = PreparedLevels()
    if len(rows) != 9 or {row.get("rule_no") for row in rows} != set(range(1, 10)):
        LOG.error("产品等级规则未完整初始化9条；等级显示--")
        prepared.invalid = True
        return prepared
    for row in sorted(rows, key=lambda row: row["rule_no"]):
        if row.get("status") == 0:
            continue
        try:
            if row.get("status") != 1 or row.get("result_level") not in LEVELS:
                raise ValueError("规则等级或状态非法")
            expression = engine.parse_expression(row["condition_expr"], "bool", allowed_variables=VARIABLES)
            used = {node.id for node in ast.walk(expression.root) if isinstance(node, ast.Name) and node.id in VARIABLES}
            prepared.rules.append((row, expression, used, None))
        except (ValueError, TypeError, KeyError, DecimalException) as exc:
            # Keep a bad rule at its priority, never silently fall through it.
            prepared.rules.append((row, None, set(), str(exc)))
    return prepared


def calculate_level(return_rate, profit_rate, sell_through_ratio, prepared):
    if prepared is None or prepared.invalid:
        return None
    env = dict(return_rate=return_rate, profit_rate=profit_rate, sell_through_ratio=sell_through_ratio)
    for row, expression, used, error in prepared.rules:
        try:
            if error:
                raise ValueError(error)
            # Do not turn missing inputs into zero, even behind a short circuit.
            if any(env[key] is None for key in used):
                return None
            if engine.interpret(expression, env):
                return row["result_level"]
        except (ValueError, KeyError, DecimalException, ZeroDivisionError) as exc:
            if row["rule_no"] not in prepared.reported:
                LOG.error("产品等级规则失败 rule_no=%s expression=%r error=%s", row["rule_no"], row.get("condition_expr"), exc)
                prepared.reported.add(row["rule_no"])
            return None
    return None


def check_rules(rows):
    if len(rows) != 9 or {row.get("rule_no") for row in rows} != set(range(1,10)):
        raise ValueError("必须提交完整9条规则，序号1至9且不能重复")
    normalized, checks = [], []
    for source in rows:
        row = {key: source.get(key) for key in ("rule_no", "status", "result_level")}
        if type(row["rule_no"]) is not int or type(row["status"]) is not int or row["status"] not in (0,1):
            raise ValueError("规则序号或启用状态非法")
        if row["result_level"] not in LEVELS:
            raise ValueError("产品等级只能为S/A/B/C")
        row["condition_expr"] = str(source.get("condition_expr") or "").strip()
        row["remark"] = str(source.get("remark") or "").strip() or None
        if len(row["remark"] or "") > 255:
            raise ValueError("说明不能超过255字符")
        error = None
        try:
            engine.parse_expression(row["condition_expr"], "bool", allowed_variables=VARIABLES)
        except (ValueError, DecimalException) as exc:
            error = str(exc)
        normalized.append(row)
        checks.append(dict(rule_no=row["rule_no"], valid=error is None, error=error))
    return sorted(normalized, key=lambda row:row["rule_no"]), dict(valid=all(row["valid"] for row in checks), rows=checks)


def list_rules():
    try:
        rows = repository.list_level_rules()
    except ProgrammingError as exc:
        if exc.args[0] == 1146:
            raise ValueError("产品等级规则表未部署，请先执行06店铺分析与采购优化.sql") from exc
        raise
    if len(rows) != 9 or {row["rule_no"] for row in rows} != set(range(1,10)):
        raise ValueError("产品等级规则表未完整初始化，请检查部署脚本")
    return dict(configs=rows, revision=repository.level_rules_revision(rows))


def save_rules(rows, revision, operator=None):
    normalized, checks = check_rules(rows)
    if not checks["valid"]:
        failed = next(row for row in checks["rows"] if not row["valid"])
        raise ValueError(f"规则{failed['rule_no']}：{failed['error']}")
    repository.save_level_rules(normalized, str(operator or "SYSTEM")[:64], revision)
    return list_rules()
