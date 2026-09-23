"""探查飞书多维表格：打印字段定义和前若干条记录，确认能取到数据。

只读，不写库、不改飞书。设计入库表结构之前先用它看清真实字段名和类型。

用法：
    # 用 .env 里配好的卖家级别表
    python scripts/feishu_bitable_probe.py

    # 或直接贴多维表格地址
    python scripts/feishu_bitable_probe.py "https://xxx.feishu.cn/base/<app_token>?table=<table_id>&view=<view_id>"

    # 多看几条，并把原始JSON落到文件里细看
    python scripts/feishu_bitable_probe.py --limit 20 --dump out.json

前置：在 Date-Project/.env 里填 FEISHU_APP_ID 和 FEISHU_APP_SECRET，
并把该应用加为这张多维表格的协作者（至少可阅读），否则会报权限类业务码。
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings
from backend.integrations.feishu.client import (
    FeishuClient,
    FeishuRequestError,
    field_text,
    parse_bitable_url,
)

# 多维表格字段类型码 -> 人话。只列常见的，未知的原样打印数字。
FIELD_TYPES = {
    1: "多行文本", 2: "数字", 3: "单选", 4: "多选", 5: "日期", 7: "复选框",
    11: "人员", 13: "电话号码", 15: "超链接", 17: "附件", 18: "关联",
    19: "查找引用", 20: "公式", 21: "双向关联", 22: "地理位置", 23: "群组",
    1001: "创建时间", 1002: "最后更新时间", 1003: "创建人", 1004: "修改人",
    1005: "自动编号",
}


def target(args):
    if args.url:
        return parse_bitable_url(args.url)
    token = settings.feishu_seller_level_app_token
    if not token:
        raise SystemExit(
            "没给地址，.env 里也没配 FEISHU_SELLER_LEVEL_APP_TOKEN。\n"
            "要么把多维表格地址作为参数传进来，要么先填这三项：\n"
            "  FEISHU_SELLER_LEVEL_APP_TOKEN / FEISHU_SELLER_LEVEL_TABLE_ID / FEISHU_SELLER_LEVEL_VIEW_ID"
        )
    return token, settings.feishu_seller_level_table_id, settings.feishu_seller_level_view_id


def plain(value):
    """把 Decimal 转成字符串再序列化，保持数字原样、不经过 float。"""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="探查飞书多维表格")
    parser.add_argument("url", nargs="?", default="", help="多维表格地址，不给则用.env里的卖家级别表")
    parser.add_argument("--limit", type=int, default=5, help="打印前几条记录，默认5")
    parser.add_argument("--dump", type=Path, default=None, help="把取到的记录原样写成JSON文件")
    args = parser.parse_args()

    app_token, table_id, view_id = target(args)
    print(f"多维表格 app_token={app_token}")
    print(f"数据表   table_id={table_id}")
    print(f"视图     view_id={view_id or '(未指定，取全表默认顺序)'}")
    print(f"接入点   {settings.feishu_endpoint}\n")

    try:
        with FeishuClient() as client:
            fields = client.list_fields(app_token, table_id)
            print(f"字段 {len(fields)} 个：")
            for item in fields:
                type_code = item.get("type")
                name = FIELD_TYPES.get(type_code, f"类型{type_code}")
                primary = "  ← 主键列" if item.get("is_primary") else ""
                print(f"  {str(item.get('field_name')):<24} {name}{primary}")

            rows = client.fetch_records(app_token, table_id, view_id, limit=args.limit)
            print(f"\n取到 {len(rows)} 条（--limit {args.limit}）：")
            names = [f.get("field_name") for f in fields]
            for i, row in enumerate(rows, 1):
                values = row.get("fields") or {}
                print(f"\n  [{i}] record_id={row.get('record_id')}")
                for name in names:
                    if name in values:
                        print(f"      {str(name):<24} {field_text(values[name])[:120]}")
    except FeishuRequestError as exc:
        print(f"\n失败：{exc}")
        print("\n常见原因：")
        print("  · 应用没被加为这张多维表格的协作者 → 在表格右上角「...」→ 添加文档应用")
        print("  · 应用没开通多维表格相关权限 → 开发者后台「权限管理」里申请并发布版本")
        print("  · FEISHU_APP_ID / FEISHU_APP_SECRET 填错或应用未启用")
        return 1

    if args.dump:
        args.dump.write_text(json.dumps(plain(rows), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n原始记录已写入 {args.dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
