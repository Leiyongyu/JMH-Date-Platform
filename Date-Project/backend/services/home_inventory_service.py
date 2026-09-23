"""首页库存看板：复用月报展示月口径；只新增SKU月度快照。"""
import json
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from backend.database import db_connection
from backend.repositories.clearance_repository import GROUP_SOURCE_SQL
from backend.services import amz_owner_sku_service, ebay_owner_sku_service

SNAPSHOT_TABLE = 'dws_home_inventory_sku_monthly'
VERSION = 1
GROUPS = {'EBAY-1', 'EU', 'US1', 'US2', 'US2-MJ', 'US1-ZXY'}
TRANSIT = ('local_end_in_transit_total_cost', 'overseas_end_in_transit_total_cost', 'fba_end_in_transit_total_cost')
STOCK = ('local_end_inventory_total_cost', 'overseas_end_inventory_total_cost', 'fba_end_inventory_total_cost')
AGE = ('inventory_0_90_cost', 'inventory_91_180_cost', 'inventory_181_plus_cost')


def current_month():
    return datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m')


def valid_month(value):
    if not isinstance(value, str) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', value):
        raise ValueError('月份必须为YYYY-MM')
    return value


def shift(month, delta):
    y, m = map(int, valid_month(month).split('-'))
    y, m = divmod(y * 12 + m - 1 + delta, 12)
    return f'{y:04d}-{m+1:02d}'


def amount(values):
    values = list(values)
    if not values or any(v is None for v in values): return None
    numbers = [Decimal(str(v)) for v in values]
    return sum(numbers, Decimal(0)) if all(n.is_finite() for n in numbers) else None


def metric(value, previous, count=False):
    delta = None if value is None or previous is None else value - previous
    ratio = None if delta is None or previous == 0 else delta / abs(previous) * 100
    def serialize(n):
        return None if n is None else int(n) if count else str(Decimal(n).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    return dict(value=serialize(value), previous=serialize(previous), delta=serialize(delta),
                change_percent=None if ratio is None else str(ratio.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)),
                direction='unknown' if delta is None else 'up' if delta > 0 else 'down' if delta < 0 else 'flat',
                comparison='missing' if delta is None else 'zero_base' if previous == 0 and delta != 0 else 'available')


def summarize_money(totals, age_rows, month):
    def money(m, fields):
        rows = [r for r in totals if str(r['stat_month']) == shift(m, -1)]
        return amount(rows[0].get(f) for f in fields) if len(rows) == 1 else None
    def age(m, field):
        rows = [r for r in age_rows if str(r['pull_month']) == m]
        if len(rows) != len(GROUPS) or {r['group_code'] for r in rows} != GROUPS: return None
        return amount(r.get(field) for r in rows)
    prev = shift(month, -1)
    buckets = {f: metric(age(month, f), age(prev, f)) for f in AGE}
    return dict(report_month=month, previous_month=prev, source_stat_month=shift(month, -1),
                inventory_total=metric(money(month, TRANSIT + STOCK), money(prev, TRANSIT + STOCK)),
                transit=metric(money(month, TRANSIT), money(prev, TRANSIT)),
                slow_total=metric(amount(age(month, f) for f in AGE[1:]), amount(age(prev, f) for f in AGE[1:])),
                age_buckets=buckets)


def inventory_summary(month=None):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        cur.execute('SELECT DISTINCT stat_month FROM dws_inventory_report_department_summary WHERE is_total=1 ORDER BY stat_month DESC')
        months = [shift(str(r['stat_month']), 1) for r in cur.fetchall()]
        selected = valid_month(month) if month else months[0] if months else current_month()
        cur.execute('''SELECT * FROM dws_inventory_report_department_summary
                       WHERE is_total=1 AND department_code='AUTO-PARTS-TOTAL' AND stat_month IN (%s,%s)''',
                    (shift(selected, -1), shift(selected, -2)))
        totals = list(cur.fetchall())
        cur.execute(f'SELECT * FROM ({GROUP_SOURCE_SQL}) age_groups WHERE pull_month IN (%s,%s)', (selected, shift(selected, -1)))
        ages = list(cur.fetchall())
        conn.rollback()
    return dict(summarize_money(totals, ages, selected), months=months,
                current_month=current_month(), currency='CNY', ctu_included=False)


def live_sku():
    month = current_month()
    summaries = {'amz': amz_owner_sku_service.get_owner_sku_counts(), 'ebay': ebay_owner_sku_service.get_owner_sku_counts()}
    for platform, report in summaries.items():
        if report.get('state') not in ('READY', 'EMPTY') or report.get('total') is None or report.get('rule_month') != month:
            raise ValueError(f'{platform.upper()}当月在售SKU统计尚未就绪，请检查刊登同步和当月负责人规则')
    return dict(rule_version=VERSION, stat_month=month,
                captured_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
                total=sum(r['total'] for r in summaries.values()),
                platforms={p: dict(total=r['total'], source_updated_at=r.get('source_updated_at'),
                                   warnings=r.get('warnings', [])) for p, r in summaries.items()})


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def sku_summary(month):
    month = valid_month(month)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT stat_month,payload_json FROM {SNAPSHOT_TABLE} WHERE stat_month IN (%s,%s)', (month, shift(month,-1)))
        snapshots = {str(r['stat_month']): decode(r['payload_json']) for r in cur.fetchall()}
    snapshots = {m: r for m,r in snapshots.items() if r.get('rule_version') == VERSION}
    warning = None
    if month == current_month():
        try: active = live_sku()
        except ValueError as exc: active, warning = None, str(exc)
    else: active = snapshots.get(month)
    previous = snapshots.get(shift(month, -1))
    return dict(report_month=month, current_month=current_month(),
                metric=metric(None if active is None else Decimal(active['total']),
                              None if previous is None else Decimal(previous['total']), count=True),
                platforms=active.get('platforms', {}) if active else {},
                captured_at=active.get('captured_at') if active else None,
                saved_at=snapshots.get(month, {}).get('captured_at'),
                previous_captured_at=previous.get('captured_at') if previous else None,
                warning=warning, live=month == current_month())


def capture_sku():
    # Only actual current-month observations; never accept a historical month from callers.
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK('jmh:home-inventory-sku',0) acquired")
        if cur.fetchone()['acquired'] != 1: raise ValueError('SKU快照正在保存，请稍后再试')
        try:
            report = live_sku()
            if report['stat_month'] != current_month(): raise ValueError('统计期间月份已变化，请重试')
            cur.execute(f'''INSERT INTO {SNAPSHOT_TABLE} (stat_month,rule_version,sku_count,amz_sku_count,ebay_sku_count,captured_at,payload_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE rule_version=VALUES(rule_version),
                sku_count=VALUES(sku_count),amz_sku_count=VALUES(amz_sku_count),ebay_sku_count=VALUES(ebay_sku_count),
                captured_at=VALUES(captured_at),payload_json=VALUES(payload_json)''',
                (report['stat_month'], VERSION, report['total'], report['platforms']['amz']['total'], report['platforms']['ebay']['total'],
                 datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None), json.dumps(report, ensure_ascii=False)))
            conn.commit()
            return report
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.execute("SELECT RELEASE_LOCK('jmh:home-inventory-sku')")
