"""测试领星本地仓库存报表接口调用。

用法：
  cd jmh-report-service
  python scripts/test_lingxing_local_inventory.py
"""

import sys
from pathlib import Path

# 项目根加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.clients.lingxing_client import LingxingClient


def test():
    client = LingxingClient(
        endpoint=settings.lingxing_endpoint,
        app_id=settings.lingxing_app_id,
        app_secret=settings.lingxing_app_secret,
        connect_timeout=settings.lingxing_connect_timeout,
        read_timeout=settings.lingxing_read_timeout,
        token_refresh_skew_seconds=settings.lingxing_token_refresh_skew_seconds,
    )

    # 1. token
    token = client.get_access_token()
    print(f"access_token ok  (len={len(token)})")

    # 2. 调接口
    result = client.get_local_inventory_report_page(
        start_date="2026-07-01",
        end_date="2026-07-01",
        offset=1,
        length=10,
    )

    code = str(result.get("code", ""))
    data = result.get("data")
    total = data.get("total") if isinstance(data, dict) else None
    rows = data.get("data") if isinstance(data, dict) else data
    row_count = len(rows) if isinstance(rows, list) else 0

    print(f"code: {code}")
    print(f"total: {total}")
    print(f"rows: {row_count}")

    if code not in ("0", "200"):
        print(f"FAILED: msg={result.get('msg','')}")
        sys.exit(1)

    if row_count > 0:
        first = rows[0]
        print(f"first row keys: {list(first.keys())}")


if __name__ == "__main__":
    test()
