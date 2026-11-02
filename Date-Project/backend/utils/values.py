"""跨模块共用的取值/清洗小工具。

两种文本清洗语义不同，按需选用，不要混用：

- ``text``：``None``、空串以及 **0 / False 等假值** 都视为空。适合 SKU、店铺名这类
  字符串字段，Excel 空单元格读成 0 时不会变成 "0"。
- ``text_keep_zero``：只有 ``None`` 视为空，数值 0 保留为 "0"。适合数量、价格
  等可能合法为 0 的单元格先转文本再解析的场景。
"""
from __future__ import annotations

from typing import Any


def text(value: Any) -> str:
    return str(value or "").strip()


def text_keep_zero(value: Any) -> str:
    return "" if value is None else str(value).strip()
