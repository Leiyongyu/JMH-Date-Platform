"""Restricted Decimal expressions for eBay replenishment v2 (no dynamic execution).

Rules are parsed once per list request, then interpreted for each SKU. Safety
bounds (not business thresholds): 500 characters, 128 AST nodes, depth 16,
50 significant digits per literal and numeric magnitudes up to 1e24.
Invalid rules stop matching; they must never silently select a lower tier.
"""
from __future__ import annotations

import ast
import logging
import operator
import re
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from typing import Any

logger = logging.getLogger(__name__)
MAX_EXPRESSION_LENGTH = 500
MAX_NODES = 128
MAX_DEPTH = 16
MAX_ABS_VALUE = Decimal("1e24")
MIN_NONZERO_VALUE = Decimal("1e-24")
VARIABLES = {"s7", "s15", "s30", "r7", "r15", "r30", "age"}
BOOL_ALIASES = {"true": True, "false": False, "True": True, "False": False}
ARITHMETIC = {ast.Add: operator.add, ast.Sub: operator.sub,
              ast.Mult: operator.mul, ast.Div: operator.truediv}
COMPARISONS = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
               ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
NUMBER_LITERAL = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
MAX_EXACT_DIGITS = 512
EXACT_PRECISION = 2 * MAX_EXACT_DIGITS + 50


def _number(value: Any) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("必须为有限Decimal数值")
    magnitude = value.copy_abs()
    if magnitude > MAX_ABS_VALUE or (magnitude and magnitude < MIN_NONZERO_VALUE):
        raise ValueError("数值超出技术安全范围（非零绝对值1e-24至1e24）")
    return value


@dataclass(frozen=True)
class ExactNumber:
    """Decimal numerator/denominator: do not round daily rates before comparison."""
    numerator: Decimal
    denominator: Decimal = Decimal(1)


def _exact(numerator: Decimal, denominator: Decimal = Decimal(1)) -> ExactNumber:
    if not denominator:
        raise ZeroDivisionError("规则表达式除以0")
    if not numerator.is_finite() or not denominator.is_finite():
        raise ValueError("表达式产生非有限数值")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    # Normalize to Decimal integers, so the digit budget also bounds exponents
    # and cross-product precision (not just the coefficient's digit count).
    shift = -min(numerator.as_tuple().exponent, denominator.as_tuple().exponent, 0)
    numerator = numerator.scaleb(shift)
    denominator = denominator.scaleb(shift)
    if max(numerator.adjusted() + 1, denominator.adjusted() + 1) > MAX_EXACT_DIGITS:
        raise ValueError("表达式中间数值位数过多")
    magnitude = numerator.copy_abs()
    if magnitude > MAX_ABS_VALUE * denominator or (
        magnitude and magnitude < MIN_NONZERO_VALUE * denominator
    ):
        raise ValueError("表达式数值超出技术安全范围")
    return ExactNumber(numerator, denominator)


def _arithmetic(op: ast.operator, left: ExactNumber, right: ExactNumber) -> ExactNumber:
    a, b = left.numerator, left.denominator
    c, d = right.numerator, right.denominator
    if isinstance(op, ast.Add):
        return _exact(a * d + c * b, b * d)
    if isinstance(op, ast.Sub):
        return _exact(a * d - c * b, b * d)
    if isinstance(op, ast.Mult):
        return _exact(a * c, b * d)
    if isinstance(op, ast.Div):
        return _exact(a * d, b * c)
    raise ValueError("不支持的数值运算")


@dataclass(frozen=True)
class Expression:
    root: ast.expr


def parse_expression(source: str, expected_type: str, allowed_variables=None) -> Expression:
    allowed = VARIABLES if allowed_variables is None else frozenset(allowed_variables)
    if not source or len(source) > MAX_EXPRESSION_LENGTH:
        raise ValueError("表达式不能为空且不能超过500字符")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        # ast.parse 抛的是 Python 原文（如 invalid syntax (<unknown>, line 1)），
        # 运营看不懂也不知道怎么改，这里换成可操作的中文提示。
        position = f"第{exc.offset}个字符附近" if exc.offset else ""
        raise ValueError(
            f"表达式语法有误{position}，请检查括号是否成对、运算符两侧是否都有内容"
        ) from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError("表达式节点过多")

    def validate(node: ast.AST, depth: int = 0) -> str:
        if depth > MAX_DEPTH:
            raise ValueError("表达式嵌套过深")
        if isinstance(node, ast.Constant):
            if type(node.value) is bool:
                return "bool"
            if type(node.value) not in (int, float):
                raise ValueError("只允许数值或布尔常量")
            # Read the original token, never Decimal(str(node.value)): the AST
            # parser may already have rounded a decimal token to binary float.
            token = (ast.get_source_segment(source, node) or "").replace("_", "")
            if not NUMBER_LITERAL.fullmatch(token):
                raise ValueError("只允许十进制数值常量")
            number = _number(Decimal(token))
            if len(number.as_tuple().digits) > 50:
                raise ValueError("数值常量有效位不能超过50位")
            node.value = number
            return "number"
        if isinstance(node, ast.Name):
            if node.id in BOOL_ALIASES:
                return "bool"
            if node.id in allowed:
                return "number"
            raise ValueError(f"未知变量 {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            if validate(node.left, depth + 1) != "number" or validate(node.right, depth + 1) != "number":
                raise ValueError("算术运算仅允许数值")
            return "number"
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.Not, ast.USub, ast.UAdd):
            kind = validate(node.operand, depth + 1)
            if kind != ("bool" if isinstance(node.op, ast.Not) else "number"):
                raise ValueError("一元运算类型不匹配")
            return kind
        if isinstance(node, ast.BoolOp) and type(node.op) in (ast.And, ast.Or):
            for child in node.values:
                if validate(child, depth + 1) != "bool":
                    raise ValueError("and/or的操作数必须为布尔值")
            return "bool"
        if isinstance(node, ast.Compare) and all(type(op) in COMPARISONS for op in node.ops):
            for child in [node.left, *node.comparators]:
                if validate(child, depth + 1) != "number":
                    raise ValueError("比较运算仅允许数值")
            return "bool"
        raise ValueError(f"不允许的语法 {type(node).__name__}")

    if validate(tree.body) != expected_type:
        raise ValueError("条件必须返回bool，公式必须返回数值")
    return Expression(tree.body)


def interpret(expression: Expression, variables: dict[str, Decimal | ExactNumber]) -> Decimal | bool:
    def visit(node: ast.expr) -> ExactNumber | bool:
        if isinstance(node, ast.Constant):
            return node.value if type(node.value) is bool else _exact(node.value)
        if isinstance(node, ast.Name):
            if node.id in BOOL_ALIASES:
                return BOOL_ALIASES[node.id]
            value = variables[node.id]
            return value if isinstance(value, ExactNumber) else _exact(_number(value))
        if isinstance(node, ast.BinOp):
            return _arithmetic(node.op, visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            if isinstance(node.op, ast.Not):
                return not value
            return _exact(-value.numerator, value.denominator) if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BoolOp):
            # Preserve short circuiting, e.g. age > 0 and s30 / age > 1.
            if isinstance(node.op, ast.And):
                return all(visit(child) for child in node.values)
            return any(visit(child) for child in node.values)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, child in zip(node.ops, node.comparators):
                right = visit(child)
                if not COMPARISONS[type(op)](
                    left.numerator * right.denominator,
                    right.numerator * left.denominator,
                ):
                    return False
                left = right
            return True
        raise ValueError("表达式未通过预解析")

    with localcontext() as context:
        # Cross-products of bounded Decimal integers/coefficients are exact.
        # Division is deferred until after rule selection, before final quantize.
        context.prec = EXACT_PRECISION
        context.Emax = 4096
        context.Emin = -4096
        result = visit(expression.root)
        return result if type(result) is bool else result.numerator / result.denominator


@dataclass(frozen=True)
class Rule:
    rule_no: int
    product_nature: str
    condition_expr: str
    formula_expr: str
    condition: Expression | None = None
    formula: Expression | None = None
    error: str | None = None


@dataclass
class PreparedRules:
    rules: tuple[Rule, ...] = ()
    invalid: bool = False
    # Request-local deduplication avoids logging the same broken rule per SKU.
    reported: set[tuple[int, str]] = field(default_factory=set)


def prepare_rules(rows: list[dict[str, Any]]) -> PreparedRules:
    prepared = PreparedRules()
    rules = []
    seen = set()
    for row in rows:
        try:
            rule_no = int(row["rule_no"])
            nature = str(row.get("product_nature") or "").strip()
            if rule_no < 1 or rule_no in seen or nature not in {"新品", "老品"}:
                raise ValueError("规则序号重复、无效或产品性质无效")
            seen.add(rule_no)
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("预估销量2规则元数据错误: %s", exc)
            prepared.invalid = True
            continue
        condition = str(row.get("condition_expr") or "").strip()
        formula = str(row.get("formula_expr") or "").strip()
        try:
            rules.append(Rule(rule_no, nature, condition, formula,
                              parse_expression(condition, "bool"),
                              parse_expression(formula, "number")))
        except (ValueError, SyntaxError, DecimalException, RecursionError) as exc:
            logger.error("预估销量2规则解析失败 rule_no=%s condition=%r formula=%r error=%s",
                         rule_no, condition, formula, exc)
            # Keep the invalid rule at its original priority; never skip it.
            rules.append(Rule(rule_no, nature, condition, formula, error=str(exc)))
    prepared.rules = tuple(sorted(rules, key=lambda rule: rule.rule_no))
    if not rows:
        logger.warning("预估销量2无启用规则，结果显示--；请检查规则表部署及配置")
    return prepared


def calculate_forecast(
    *, product_nature: str | None, sales_7d: Decimal, sales_15d: Decimal,
    sales_30d: Decimal, age_days: Decimal | None, rules: PreparedRules,
    trace: dict[str, Any] | None = None,
    round_result: bool = True,
) -> Decimal | None:
    # Optional diagnostics use the exact same execution path as the list.
    if trace is not None:
        trace.clear()
        trace.update(status="unavailable", matched_rule_no=None, value=None)
    if product_nature not in {"新品", "老品"} or rules.invalid or not rules.rules:
        if trace is not None:
            trace["message"] = "产品性质未知或没有可用规则，结果显示--"
        return None
    if product_nature == "新品" and (age_days is None or not age_days.is_finite() or age_days <= 0):
        if trace is not None:
            trace.update(status="missing_age", message="新品库龄缺失或不大于0，前置检查返回--，未执行规则公式")
        return None
    active_rule = None
    try:
        with localcontext() as context:
            context.prec = 50
            context.Emax = 48
            context.Emin = -48
            s7, s15, s30 = (_number(value) for value in (sales_7d, sales_15d, sales_30d))
            if min(s7, s15, s30) < 0:
                raise ValueError("销量不能为负数")
            variables = {"s7": s7, "s15": s15, "s30": s30,
                         "r7": _exact(s7, Decimal(7)), "r15": _exact(s15, Decimal(15)),
                         "r30": _exact(s30, Decimal(30)),
                         "age": _number(age_days) if age_days is not None else Decimal(0)}
            for rule in rules.rules:
                if rule.product_nature != product_nature:
                    continue
                active_rule = rule
                if rule.error:
                    if trace is not None:
                        trace.update(status="invalid_rule", failed_rule_no=rule.rule_no,
                                     message=rule.error)
                    return None  # already logged during preparation
                matched = interpret(rule.condition, variables)
                if type(matched) is not bool:
                    raise ValueError("条件结果不是bool")
                if not matched:
                    continue
                if trace is not None:
                    trace.update(matched_rule_no=rule.rule_no,
                                 condition_expr=rule.condition_expr, formula_expr=rule.formula_expr)
                value = _number(interpret(rule.formula, variables))
                if value < 0:
                    raise ValueError("预估销量结果不能为负数")
                result = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if trace is not None:
                    trace.update(status="matched", value=format(result, "f"),
                                 message=f"命中规则{rule.rule_no}")
                # Display/preview retains 2 decimals; downstream stock formulas can
                # request the unrounded Decimal to avoid a second rounding boundary.
                return result if round_result else value
    except (ValueError, DecimalException, ArithmeticError, TypeError) as exc:
        rule_no = active_rule.rule_no if active_rule else 0
        key = (rule_no, str(exc))
        if key not in rules.reported:
            rules.reported.add(key)
            logger.error("预估销量2计算失败 rule_no=%s condition=%r formula=%r error=%s",
                         rule_no, active_rule.condition_expr if active_rule else "",
                         active_rule.formula_expr if active_rule else "", exc)
        if trace is not None:
            trace.update(status="calculation_error", failed_rule_no=rule_no,
                         message=f"计算失败，结果显示--：{exc}")
        return None
    if trace is not None:
        trace.update(status="no_match", message="没有启用规则命中，结果显示--")
    return None
