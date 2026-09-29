"""库存明细专用核心码规则；不影响补货或海外仓库龄占比。"""
import re


def normalize_core_code(value) -> str | None:
    """标识符按文本保留前导零，支持数字及混合字母，排除品牌等纯字母段。"""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().upper()
    return text if re.fullmatch(r"(?=[A-Z0-9]*[0-9])[A-Z0-9]{1,64}", text) else None


def sku_core_code(sku) -> str | None:
    parts = str(sku or "").strip().split("-")
    return normalize_core_code(parts[1]) if len(parts) > 1 else None
