"""calculate：在本次已查到的工具结果上做精确计算（环比/同比、两次结果对比、占比、排名、合计）。

只读取本次运行里已经按权限取到的数据，不访问数据库，也不执行任意表达式；
列可以用中文列名或字段名指定。比例列（如毛利率）的差值按百分点给出。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agent.tools.base import ToolResult

TOTAL_LABELS = {"合计", "总计", "全部"}
RATIO_HINTS = ("率", "rate", "margin", "ratio", "占比")


class CalculateArgs(BaseModel):
    operation: Literal["period_compare", "compare", "share", "rank", "sum", "count"] = Field(
        ..., description="period_compare=同一结果内两个期间对比（环比/同比）；compare=两个结果按维度对比；"
                         "share=占合计比例；rank=排名；sum=合计；count=按维度列分组计数（如每个国家几个店铺）")
    result_id: int = Field(..., ge=1, description="要计算的工具结果编号 result_id")
    value_columns: list[str] = Field(default_factory=list, max_length=6,
                                     description="数值列（中文列名或字段名）；count 不需要")
    key_column: str | None = Field(None, description="维度列，如 组别、负责人、SKU；share/rank/compare 必填")
    period_column: str | None = Field(None, description="period_compare 用：期间列，如 月份")
    base_period: str | None = Field(None, description="period_compare 用：基期，如 2026-08")
    target_period: str | None = Field(None, description="period_compare 用：比较期，如 2026-09")
    other_result_id: int | None = Field(None, ge=1, description="compare 用：另一个结果编号（作为比较期）")
    top: int = Field(50, ge=1, le=200)


class CalculationError(ValueError):
    pass


def _column(result: dict[str, Any], name: str | None, what: str) -> tuple[str, str]:
    if not name:
        raise CalculationError(f"请提供{what}")
    for column in result.get("columns") or []:
        if name in (column["key"], column["label"]):
            return column["key"], column["label"]
    labels = "、".join(c["label"] for c in result.get("columns") or [])
    raise CalculationError(f"结果{result.get('id')}中没有列「{name}」，可用列：{labels}")


def _number(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _is_ratio(key: str, label: str) -> bool:
    return any(hint in key.lower() or hint in label for hint in RATIO_HINTS)


def _round(value: Decimal | None, ratio: bool) -> float | None:
    if value is None:
        return None
    return float(round(value, 4 if ratio else 2))


def _change(base: Decimal | None, target: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    if base is None or target is None:
        return None, None
    diff = target - base
    return diff, (diff / abs(base)) if base != 0 else None


def _pick(results: list[dict[str, Any]], result_id: int) -> dict[str, Any]:
    if not 1 <= result_id <= len(results):
        raise CalculationError(f"不存在结果编号 {result_id}，本次共有 {len(results)} 个结果")
    return results[result_id - 1]


def _data_rows(result: dict[str, Any], key: str | None) -> list[dict[str, Any]]:
    return [r for r in result.get("rows") or [] if not key or str(r.get(key)) not in TOTAL_LABELS]


def calculate(results: list[dict[str, Any]], args: CalculateArgs) -> ToolResult:
    source = _pick(results, args.result_id)
    if args.operation == "count":
        return _count(source, args)
    if not args.value_columns:
        raise CalculationError("请提供数值列 value_columns")
    values = [_column(source, name, "数值列") for name in args.value_columns]

    if args.operation in ("period_compare", "compare"):
        key, key_label = _column(source, args.key_column, "维度列（key_column）")
        if args.operation == "period_compare":
            period_key, _ = _column(source, args.period_column, "期间列（period_column）")
            if not args.base_period or not args.target_period:
                raise CalculationError("period_compare 需要 base_period 和 target_period")
            base_rows = {r.get(key): r for r in source["rows"] if str(r.get(period_key)) == args.base_period}
            target_rows = {r.get(key): r for r in source["rows"] if str(r.get(period_key)) == args.target_period}
            base_name, target_name = args.base_period, args.target_period
        else:
            if not args.other_result_id:
                raise CalculationError("compare 需要 other_result_id")
            other = _pick(results, args.other_result_id)
            other_key, _ = _column(other, args.key_column, "维度列（key_column）")
            base_rows = {r.get(key): r for r in source["rows"]}
            target_rows = {r.get(other_key): r for r in other["rows"]}
            base_name, target_name = f"结果{args.result_id}", f"结果{args.other_result_id}"
            values = [(k, l) for k, l in values if any(c["key"] == k for c in other.get("columns") or [])]
            if not values:
                raise CalculationError("两个结果没有同名数值列，无法对比")
        if not base_rows or not target_rows:
            raise CalculationError(f"没有找到「{base_name}」或「{target_name}」的数据")
        columns: list[tuple[str, str]] = [("key", key_label)]
        for value_key, label in values:
            ratio = _is_ratio(value_key, label)
            columns += [(f"{value_key}__base", f"{label}（{base_name}）"),
                        (f"{value_key}__target", f"{label}（{target_name}）"),
                        (f"{value_key}__diff", f"{label}变化" + ("（百分点）" if ratio else ""))]
            if not ratio:
                columns.append((f"{value_key}__rate", f"{label}变化率"))
        rows = []
        for item in list(dict.fromkeys([*base_rows, *target_rows])):
            row: dict[str, Any] = {"key": item}
            for value_key, label in values:
                ratio = _is_ratio(value_key, label)
                base = _number((base_rows.get(item) or {}).get(value_key))
                target = _number((target_rows.get(item) or {}).get(value_key))
                diff, rate = _change(base, target)
                row[f"{value_key}__base"] = _round(base, ratio)
                row[f"{value_key}__target"] = _round(target, ratio)
                # 比例列差值换算成百分点，便于直接引用（0.0125 → 1.25 个百分点）
                row[f"{value_key}__diff"] = _round(diff * 100, False) if ratio and diff is not None else _round(diff, ratio)
                if not ratio:
                    row[f"{value_key}__rate"] = _round(rate, True)
            rows.append(row)
        notes = ["变化 = 比较期 − 基期；变化率 = 变化 ÷ |基期|（小数）；比例列的变化单位为百分点"]
        title = f"对比计算：{base_name} → {target_name}"
    elif args.operation == "share":
        key, key_label = _column(source, args.key_column, "维度列（key_column）")
        data = _data_rows(source, key)
        columns, rows = [("key", key_label)], [{"key": r.get(key)} for r in data]
        for value_key, label in values:
            total = sum((_number(r.get(value_key)) or Decimal(0) for r in data), Decimal(0))
            columns += [(value_key, label), (f"{value_key}__share", f"{label}占比")]
            for row, source_row in zip(rows, data):
                value = _number(source_row.get(value_key))
                row[value_key] = _round(value, False)
                row[f"{value_key}__share"] = _round(value / total, True) if value is not None and total else None
        notes = ["占比 = 该行 ÷ 各行合计（不含合计行）的小数"]
        title = "占比计算"
    elif args.operation == "rank":
        key, key_label = _column(source, args.key_column, "维度列（key_column）")
        value_key, label = values[0]
        data = sorted(_data_rows(source, key), key=lambda r: _number(r.get(value_key)) or Decimal("-1e30"),
                      reverse=True)
        columns = [("rank", "名次"), ("key", key_label), (value_key, label)]
        rows = [{"rank": index, "key": r.get(key), value_key: _round(_number(r.get(value_key)), _is_ratio(value_key, label))}
                for index, r in enumerate(data, start=1)]
        notes = [f"按{label}从高到低排名"]
        title = f"按{label}排名"
    else:
        key = _column(source, args.key_column, "维度列")[0] if args.key_column else None
        data = _data_rows(source, key)
        columns, row = [], {}
        for value_key, label in values:
            numbers = [n for n in (_number(r.get(value_key)) for r in data) if n is not None]
            columns.append((value_key, f"{label}合计"))
            row[value_key] = _round(sum(numbers, Decimal(0)), False) if numbers else None
        rows = [row]
        notes = ["合计不含合计行；比例列不应直接相加，请改用原结果中的合计行"]
        title = "合计计算"
    return ToolResult(title=title, columns=columns, rows=rows[:args.top], source=f"基于结果{args.result_id}计算",
                      period=source.get("period") or "", notes=notes,
                      summary={"计算方式": args.operation, "行数": len(rows)})


def _count(source: dict[str, Any], args: CalculateArgs) -> ToolResult:
    """按维度列分组计数，使用完整结果（不受交给模型的 30 行限制）。"""
    key, label = _column(source, args.key_column, "维度列（key_column）")
    counts: dict[Any, int] = {}
    for row in _data_rows(source, key):
        counts[row.get(key)] = counts.get(row.get(key), 0) + 1
    rows = [{"key": k, "count": n} for k, n in sorted(counts.items(), key=lambda item: -item[1])]
    total = sum(counts.values())
    notes = [f"共 {total} 行，按{label}分为 {len(rows)} 组"]
    stored = len(source.get("rows") or [])
    if (source.get("rowCount") or stored) > stored:
        notes.append(f"原结果共 {source.get('rowCount')} 行，只保存了前 {stored} 行，计数基于已保存的行")
    return ToolResult(title=f"按{label}计数", columns=[("key", label), ("count", "行数")], rows=rows[:args.top],
                      source=f"基于结果{args.result_id}计算", period=source.get("period") or "", notes=notes,
                      summary={"计算方式": "count", "总行数": total, "分组数": len(rows)})
