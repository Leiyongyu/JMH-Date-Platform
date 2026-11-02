"""回答数字核对：回答里的金额、比例、数量必须能在本次工具结果里找到。

规则（宁可漏报，不误伤正常回答）：
- 只核对百分比和绝对值 ≥ 100 的数；日期、月份、名次、「前5名」这类小整数不核对；
- 按回答里写出的精度判断是否一致：「15.80%」容差 0.005 个百分点，「约 368 万」容差 0.5 万；
- 比例类字段（小数）同时按 ×100 的百分数比较；不区分正负号（「下降 4.7%」对应 -0.047）；
- `[[表:N]]` 引用的是后端表格，不在核对范围；用户提问里出现过的数字视为已知。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

TABLE_REF = re.compile(r"\[\[表:\d+\]\]")
DATE_LIKE = re.compile(
    r"20\d{2}\s*[-/年.]\s*\d{1,2}(\s*[-/月.]\s*\d{1,2}\s*日?)?|\d{1,2}\s*月\s*\d{1,2}\s*日|\d{1,2}:\d{2}"
)
# SKU、订单号、ASIN 等编码里的数字不是金额，整段去掉（如 DAS-10071-0040、123-4567890-1234567）。
CODE_LIKE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+|B0[A-Z0-9]{8}")
# 只排除紧跟在英文字母/数字后面的数字（中文字符在 \w 里，不能用 \w，否则「是5000」会漏掉）
NUMBER = re.compile(
    r"(?<![A-Za-z0-9_.])([-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+−]?\d+(?:\.\d+)?)\s*(%|％|万|亿)?"
)
STRING_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
SCALE = {"万": Decimal(10000), "亿": Decimal(100000000)}
MIN_CHECKED = Decimal(100)


@dataclass(frozen=True)
class AnswerNumber:
    raw: str
    value: Decimal
    percent: bool
    tolerance: Decimal


@dataclass
class Verification:
    status: str  # passed / warned / skipped
    checked: int = 0
    unmatched: list[str] = field(default_factory=list)
    repaired: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "checked": self.checked, "unmatched": self.unmatched,
                "repaired": self.repaired}


def extract_numbers(text: str) -> list[AnswerNumber]:
    cleaned = CODE_LIKE.sub(" ", DATE_LIKE.sub(" ", TABLE_REF.sub(" ", text or "")))
    numbers: list[AnswerNumber] = []
    for match in NUMBER.finditer(cleaned):
        raw_number, unit = match.group(1), match.group(2)
        digits = raw_number.replace(",", "").replace("−", "-").lstrip("+")
        try:
            base = Decimal(digits)
        except InvalidOperation:
            continue
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        step = Decimal(1).scaleb(-decimals) / 2
        if unit in ("%", "％"):
            numbers.append(AnswerNumber(match.group(0).strip(), abs(base), True, step))
            continue
        if not unit and decimals == 0 and 1990 <= base <= 2100:
            continue  # 年份
        scale = SCALE.get(unit or "", Decimal(1))
        value = abs(base * scale)
        if value < MIN_CHECKED:
            continue
        numbers.append(AnswerNumber(match.group(0).strip(), value, False, step * scale))
    return numbers


def _walk(value: Any) -> Iterable[Decimal]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float, Decimal)):
        yield abs(Decimal(str(value)))
    elif isinstance(value, str):
        # 文字里的数字也算已知（如口径说明「库龄 181 天以上」、提示「仅展示前30行」）
        for text in STRING_NUMBER.findall(value.replace(",", "")):
            yield abs(Decimal(text))
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def known_values(results: list[dict[str, Any]]) -> tuple[list[Decimal], list[Decimal]]:
    """返回（绝对值候选, 百分数候选）。比例小数 ×100 后进入百分数候选。"""
    absolute: set[Decimal] = set()
    percent: set[Decimal] = set()
    for result in results:
        fields = [result.get(key) for key in ("title", "period", "summary", "notes", "rows", "rowCount")]
        for number in _walk(fields):
            absolute.add(number)
            percent.add(number)
            if number <= Decimal(5):  # 比例以小数存放（0.1159 = 11.59%）
                percent.add(number * 100)
    return sorted(absolute), sorted(percent)


def _matches(number: AnswerNumber, candidates: list[Decimal]) -> bool:
    tolerance = number.tolerance + Decimal("0.000001")
    return any(abs(candidate - number.value) <= tolerance for candidate in candidates)


def verify(answer: str, results: list[dict[str, Any]], question: str = "") -> Verification:
    if not results:
        return Verification("skipped")
    numbers = extract_numbers(answer)
    if not numbers:
        return Verification("passed")
    absolute, percent = known_values(results)
    asked = {n.value for n in extract_numbers(question)}
    unmatched = []
    for number in numbers:
        if number.value in asked:
            continue
        if not _matches(number, percent if number.percent else absolute):
            unmatched.append(number.raw)
    unique = list(dict.fromkeys(unmatched))
    return Verification("warned" if unique else "passed", checked=len(numbers), unmatched=unique)


def repair_instruction(unmatched: list[str]) -> str:
    return (
        "回答中的这些数字在本次工具结果里找不到：" + "、".join(unmatched[:20]) + "。"
        "如果是环比、差值、占比、合计等派生数字，请调用 calculate 工具计算后再引用；"
        "如果是抄写错误请改正；无法核实的请删除。然后重新给出完整回答，不要提及本条检查。"
    )
