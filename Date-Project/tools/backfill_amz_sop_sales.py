"""一次性按月回填 AMZ-SOP 销量快照（自然月），并重建 DWS 汇总。

领星 OrderProfit 令牌桶容量=1，严格限流；本脚本每次请求之间间隔足够长，
限流时指数退避重试。运行：python -u backfill_amz_sop_sales.py
"""
import time
from datetime import date
from uuid import uuid4

import pymysql

from backend.config import settings
from backend.integrations.lingxing.domains.order_profit import LingXingOrderProfitDomain
from backend.repositories import amz_sop_repository as repo
from backend.services.amz_sop_after_sales_service import _transform_sales_period


def _month_end(month_start: date, cap: date) -> date:
    if month_start.month == 12:
        nxt = date(month_start.year + 1, 1, 1)
    else:
        nxt = date(month_start.year, month_start.month + 1, 1)
    return min(date.fromordinal(nxt.toordinal() - 1), cap)


def _clear_sales_and_summary() -> None:
    conn = pymysql.connect(
        host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password,
        database=settings.mysql_database, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ods_amz_sop_sales_daily")
            cur.execute("DELETE FROM dwd_amz_sop_sales_daily")
            cur.execute("DELETE FROM dws_amz_sop_after_sales_summary")
        conn.commit()
    finally:
        conn.close()


def _fetch_with_retry(domain, sids, start, end):
    for attempt in range(6):
        try:
            return domain.fetch_monthly_profit(sids, start, end, currency_code="原币种")
        except RuntimeError as exc:
            wait = 10 * (attempt + 1)
            print(f"  [限流/失败] {str(exc)[:60]} -> 退避 {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"拉取 {start}~{end} 失败")


def main() -> None:
    today = date.today()
    start_month = date(today.year, 1, 1)
    end_month = date(today.year, today.month, 1)

    shops = repo.shop_map()
    sids = sorted(shops)
    if not sids:
        raise ValueError("shop_list 中没有可用的 Amazon 店铺 SID")
    print(f"回填 {start_month} ~ {today}，店铺 {len(sids)} 个", flush=True)

    _clear_sales_and_summary()
    print("已清空销量快照与 DWS 汇总", flush=True)

    domain = LingXingOrderProfitDomain()
    batch_id = f"QUANTITY-V3-BACKFILL-{uuid4()}"

    month_starts = []
    cursor = start_month
    while cursor <= end_month:
        month_starts.append(cursor)
        cursor = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)

    for month_start in month_starts:
        month_end = _month_end(month_start, today)
        remote = _fetch_with_retry(domain, sids, month_start, month_end)
        ods_rows, dwd_rows, skipped = _transform_sales_period(
            month_start, month_end, remote, shops, batch_id
        )
        repo.replace_sales_period(month_start, month_end, ods_rows, dwd_rows)
        print(
            f"{month_start}~{month_end}: remote={len(remote)} "
            f"ods={len(ods_rows)} dwd={len(dwd_rows)} skipped={skipped}", flush=True
        )
        time.sleep(6)  # 领星令牌桶容量=1

    from backend.services.amz_sop_after_sales_service import ensure_range_summary
    ensure_range_summary(start_month, today)
    print("汇总已重建：", start_month, "~", today, flush=True)
    print("backfill done, batch_id =", batch_id, flush=True)


if __name__ == "__main__":
    main()
