"""把飞书「不良交易刊登」的历史全量灌进本地表；默认只试算，不写库。

平时的每周同步只拉视图那一批（当周约370条）。首次上线时需要这个脚本把26周的
历史（实测10655条）一次性补齐；之后不需要再跑。

用法：
    python scripts/feishu_bad_transaction_backfill.py            # 试算，只打印将写入什么
    python scripts/feishu_bad_transaction_backfill.py --apply    # 真正写库

写库走的是和每周同步同一套 upsert：按 record_id 增量，内容没变的不写。
所以重复执行是安全的，第二次跑应当全部落在"未变"。
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings
from backend.integrations.feishu.client import FeishuClient, FeishuRequestError
from backend.services import feishu_bad_transaction_sync_service as service


def main() -> int:
    parser = argparse.ArgumentParser(description="飞书不良交易刊登全量回填")
    parser.add_argument("--apply", action="store_true", help="真正写库；不加时只试算")
    args = parser.parse_args()

    app_token = settings.feishu_bad_transaction_app_token
    table_id = settings.feishu_bad_transaction_table_id
    print(f"多维表格 {app_token} / 数据表 {table_id} / 全表（不带视图）")

    if args.apply:
        result = service.sync_feishu_bad_transactions(full=True)
        print(f"\n已写入：新增 {result['inserted_rows']}、更新 {result['updated_rows']}、"
              f"未变 {result['unchanged_rows']}、删除 {result['deleted_rows']}")
        print(f"覆盖批次 {len(result['batches'])} 个：{result['batches'][:3]} ... {result['batches'][-3:]}")
        for note in result["warnings"]:
            print("  提醒:", note)
        return 0

    try:
        with FeishuClient() as client:
            records = client.fetch_records(app_token, table_id, "", automatic_fields=True)
    except FeishuRequestError as exc:
        print(f"拉取失败：{exc}")
        return 1

    warnings = set()
    rows = [service.to_row(record, warnings) for record in records]
    batches = collections.Counter(str(row["reg_date"]) for row in rows)
    print(f"\n可回填 {len(rows)} 条，覆盖 {len(batches)} 个登记日期：")
    for date, count in sorted(batches.items()):
        print(f"   {date:<12} {count} 条")
    print(f"\n唯一record_id {len({r['record_id'] for r in rows})} 个"
          f"（与总条数相等才正常）")
    for note in sorted(warnings):
        print("  提醒:", note)
    print("\n试算模式，未写库。确认无误后加 --apply 重跑。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
