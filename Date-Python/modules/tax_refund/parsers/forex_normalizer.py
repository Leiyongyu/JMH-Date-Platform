"""外汇数据标准化 — 日期/金额/汇率/报关单号清洗"""
import re
import hashlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def normalize_customs_no(raw):
    """报关单号取前18位字符串"""
    if not raw: return None
    return str(raw).strip()[:18]


def _to_decimal(val):
    """转 Decimal，- / #N/A / 空 → None"""
    if val is None: return None
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    text = str(val).strip()
    if not text or text in ('-', '#N/A', '#REF!', '#VALUE!', ''):
        return None
    try:
        return Decimal(text.replace(',', '').replace(' ', ''))
    except (InvalidOperation, ValueError):
        return None


def normalize_exchange_rate(raw):
    """汇率: 716.06 → 7.1606; <20 的保持不变"""
    d = _to_decimal(raw)
    if d is None: return None
    return d / Decimal('100') if d > Decimal('20') else d


def normalize_date(val):
    """日期标准化: Excel日期对象/序列值/文本 → date"""
    if val is None: return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    text = str(val).strip()
    if not text or text in ('-', '#N/A', '#REF!', ''):
        return None
    # 纯数字序列值 (Excel serial)
    if re.match(r'^\d{4,5}$', text):
        try:
            from datetime import timedelta
            return date(1899, 12, 30) + timedelta(days=int(text))
        except: pass
    # 数字含小数
    if re.match(r'^\d+\.\d+$', text):
        try:
            from datetime import timedelta
            return date(1899, 12, 30) + timedelta(days=int(float(text)))
        except: pass
    # 异常日期如 206/2/6 → None + 标记
    if re.match(r'^\d{2,3}/\d{1,2}/\d{1,2}$', text):
        return None  # 只记录，不猜测
    # 标准格式
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y%m%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def is_abnormal_date(val):
    """判断原始日期值是否为异常格式"""
    if val is None: return False
    if isinstance(val, (date, datetime)): return False
    text = str(val).strip()
    return bool(re.match(r'^\d{2,3}/\d{1,2}/\d{1,2}$', text))


def make_receipt_business_key(core_tx_no, business_entity, receipt_date, receipt_total_usd,
                              settlement_rmb):
    """生成回款业务唯一指纹"""
    if core_tx_no:
        raw = f'{core_tx_no.strip()}'
    else:
        raw = f'{business_entity or ""}|{receipt_date or ""}|{receipt_total_usd or ""}|{settlement_rmb or ""}'
    return hashlib.sha256(raw.encode()).hexdigest()
