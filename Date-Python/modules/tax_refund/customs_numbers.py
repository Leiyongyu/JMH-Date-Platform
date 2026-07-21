"""报关单基础编号与21位商品编号规则。"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


def customs_base_number(value: Any) -> str:
    """返回报关单前18位基础编号；来源已带商品项号时自动去掉。"""
    text = re.sub(r"\s+", "", str(value or "").strip())
    if len(text) < 18:
        raise ValueError(f"报关单号必须至少18位，当前为{text!r}")
    return text[:18]


def customs_item_number(customs_declaration_no: Any, customs_item_no: Any) -> str:
    """组成数据库保存值：18位报关单基础编号 + 3位商品项号。"""
    base = customs_base_number(customs_declaration_no)
    try:
        item = int(Decimal(str(customs_item_no).strip()))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"报关商品项号不合法: {customs_item_no!r}") from None
    if item < 1 or item > 999:
        raise ValueError(f"报关商品项号必须在1到999之间: {item}")
    return f"{base}{item:03d}"
