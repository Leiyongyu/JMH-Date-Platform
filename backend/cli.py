from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.config import settings
from backend.database import init_database
from backend.services.export_service import generate_final_package
from backend.services.import_service import (
    import_customs_declaration_excel,
    import_foreign_exchange_receipts,
    import_purchase_invoice_summary,
)
from backend.services.lingxing_service import probe, refresh_token, token_status


IMPORTERS = {
    "import-customs": import_customs_declaration_excel,
    "import-purchase-summary": import_purchase_invoice_summary,
    "import-receipts": import_foreign_exchange_receipts,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="退税Excel数据库工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="初始化数据库表")
    subparsers.add_parser("export-final", help="执行保留的最终模板生成逻辑")
    token_parser = subparsers.add_parser("lingxing-token", help="查看或刷新领星Token")
    token_parser.add_argument("--show", action="store_true", help="查看Token状态")
    token_parser.add_argument("--refresh", action="store_true", help="强制刷新Token")
    probe_parser = subparsers.add_parser("lingxing-probe", help="调用领星接口探测")
    probe_parser.add_argument("--path", required=True)
    probe_parser.add_argument("--body", default="{}", help="JSON请求体")
    for command, label in (
        ("import-customs", "报关单"),
        ("import-purchase-summary", "采购发票汇总"),
        ("import-receipts", "外汇回款汇总"),
    ):
        command_parser = subparsers.add_parser(command, help=f"导入{label}Excel")
        command_parser.add_argument("--file", required=True)
    args = parser.parse_args()

    if args.command == "init-db":
        init_database()
        print(f"数据库 {settings.mysql_database} 初始化完成")
        return
    if args.command == "export-final":
        result = generate_final_package()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "lingxing-token":
        result = refresh_token() if args.refresh else token_status()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    if args.command == "lingxing-probe":
        result = probe(args.path, json.loads(args.body))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    path = Path(args.file)
    result = IMPORTERS[args.command](path.read_bytes(), path.name)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
