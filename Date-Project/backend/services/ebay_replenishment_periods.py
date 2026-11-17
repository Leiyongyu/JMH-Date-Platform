"""补货2.0统一时间口径：北京时间当天零点之前的连续90天。"""
from datetime import date, datetime, timedelta, timezone


def reference_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def rolling_periods(reference_date: date | None = None) -> list[dict]:
    end = reference_date or reference_today()
    periods = []
    for index in range(3):
        stop = end - timedelta(days=30 * index)
        start = stop - timedelta(days=30)
        periods.append({
            "month": f"{start.isoformat()} ~ {(stop - timedelta(days=1)).isoformat()}",
            "start_date": start, "end_date": stop,
        })
    return periods
