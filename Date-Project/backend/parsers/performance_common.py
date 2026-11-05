from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


# Owner workbooks historically used ``YYYYMM负责人`` while the current
# company template uses the cleaner ``YYYYMM`` header. Keep the legacy form
# readable for the platform-specific import endpoints.
MONTH_HEADER_RE = re.compile(r"^(20\d{2})(0[1-9]|1[0-2])(?:负责人)?$")
MONTH_IN_FILENAME_RE = re.compile(r"(20\d{2})(0[1-9]|1[0-2])")
STAT_MONTH_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")

EU_UK_FIXED_OWNER = "吴清栩"

# The single owner label for profit rows that match no rule. Shared so the
# ranking reader, the ETL and the unmatched diagnostics cannot drift apart.
UNASSIGNED = "未分配"

# Owner cells that mean "deliberately not assigned yet".
PENDING_OWNER_TEXTS = {"待定", "待到"}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    # pandas/numpy use NaN/NaT/NA sentinels for empty Excel cells. Converting
    # those sentinels directly to text previously created fake people named
    # ``nan`` in future-month owner columns.
    try:
        if value != value:
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).replace("\u3000", " ").replace("\xa0", " ").strip()
    return "" if text.casefold() in {"nan", "nat", "<na>", "none", "null"} else text


def normalize_principal(value: Any) -> str:
    text = normalize_text(value)
    return UNASSIGNED if text in {"", *PENDING_OWNER_TEXTS} else text


def owner_is_blank(value: Any) -> bool:
    """True when an owner cell carries no real person for that month."""
    return normalize_text(value) in {"", *PENDING_OWNER_TEXTS}


def owner_is_invisible_whitespace(value: Any) -> bool:
    """True when an owner cell looks filled but holds only blank characters.

    ``str.strip()`` drops U+3000 and U+00A0, so Python reads these cells as
    empty, while MySQL ``TRIM()`` keeps them and the eBay ranking SQL then
    treats the cell as a real owner name. Such a rule row therefore behaves
    differently on the two platforms and has to be fixed in the workbook.
    """
    if value is None:
        return False
    raw = str(value)
    return raw != "" and raw.strip() == "" and (
        "　" in raw or "\xa0" in raw
    )


def stat_month_from_yyyymm(yyyymm: str) -> str:
    return f"{yyyymm[:4]}-{yyyymm[4:]}"


def extract_month_from_filename(file_name: str) -> str:
    match = MONTH_IN_FILENAME_RE.search(Path(file_name).name)
    if not match:
        raise ValueError("文件名必须包含合法年月，例如 202606")
    return f"{match.group(1)}-{match.group(2)}"


def normalize_stat_month(value: Any) -> str:
    stat_month = normalize_text(value)
    if not STAT_MONTH_RE.fullmatch(stat_month):
        raise ValueError("统计月份必须使用YYYY-MM格式")
    return stat_month


def parse_month_header(header: Any) -> str | None:
    text = normalize_text(header)
    match = MONTH_HEADER_RE.match(text)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.000000")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    text = normalize_text(value)
    # LingXing/eBay exports use "-" or "--" as the no-data placeholder, most
    # visibly in the eBay profit sheet's 售出数 column for SKUs with no sales
    # that month. Treat them as zero instead of failing the whole import.
    if text in {"", "-", "--"}:
        return Decimal("0.000000")
    negative = text.startswith("(") and text.endswith(")")
    text = (
        text.strip("()")
        .replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("$", "")
        .replace(" ", "")
    )
    try:
        value_decimal = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"金额格式不正确: {value}") from exc
    if negative:
        value_decimal = -value_decimal
    return value_decimal.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def parse_brand_code_from_sku(sku: str) -> str:
    parts = [part for part in normalize_text(sku).split("-") if part]
    if not parts:
        return "UNKNOWN"
    if re.match(r"^[0-9]+PC$", parts[0], flags=re.IGNORECASE) and len(parts) >= 2:
        return parts[1].upper()
    return parts[0].upper()
