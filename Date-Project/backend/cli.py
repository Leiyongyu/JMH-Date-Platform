from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.config import settings
from backend.database import bootstrap_legacy_schema
from backend.infrastructure import migrations
from backend.services.export_service import generate_final_package
from backend.services.import_service import (
    import_customs_declaration_excel,
    import_foreign_exchange_receipts,
    import_purchase_invoice_summary,
)
from backend.services.inventory_report_etl_service import (
    refresh_monthly_inventory_sales_snapshot,
)
from backend.services.lingxing_service import probe, refresh_token, token_status


IMPORTERS = {
    "import-customs": import_customs_declaration_excel,
    "import-purchase-summary": import_purchase_invoice_summary,
    "import-receipts": import_foreign_exchange_receipts,
}


def _run_migration_command(args) -> None:
    for target in migrations.resolve_targets(args.target):
        if args.command == "db-status":
            states = migrations.status(target)
            print(f"[{target.name}] {target.database}  目录 {target.directory}")
            for state in states:
                if state.state in {"applied", "baseline"}:
                    continue
                suffix = f"  {state.error_message}" if state.error_message else ""
                print(f"  {state.state:<8} {state.version}{suffix}")
            done = sum(1 for s in states if s.state in {"applied", "baseline"})
            print(f"  已执行/基线 {done} 个，待处理 {len(states) - done} 个")
        elif args.command == "db-baseline":
            if target.name == "date":
                # 先补齐启动时一直自动执行的历史建表脚本，保证登记与库结构一致。
                bootstrap_legacy_schema()
            if target.managed_from_start:
                print(f"[{target.name}] 新库由迁移从头管理，无需登记基线，请直接 db-migrate")
                continue
            count = migrations.baseline(target, through=args.through)
            print(f"[{target.name}] 登记基线 {count} 个迁移")
        else:
            versions = migrations.migrate(target, dry_run=args.dry_run)
            verb = "将执行" if args.dry_run else "已执行"
            print(f"[{target.name}] {verb} {len(versions)} 个迁移")
            for version in versions:
                print(f"  {version}")


def _run_inventory_sales_refresh(args) -> None:
    result = refresh_monthly_inventory_sales_snapshot(
        args.report_month, trigger="cli", dry_run=args.dry_run,
    )
    changes = result.get("changes", [])
    if args.output:
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    print(
        f"展示月份 {result['report_month']} -> 快照 {result['stat_month']}："
        f"{result['status']}，变更 {result.get('changed_rows', 0)} 行 / "
        f"{result.get('changed_fields', 0)} 个字段"
    )
    for text in (result.get("reason"), *result.get("pending_reasons", [])):
        if text:
            print(f"  提示：{text}")
    # 组别页面全部列出；店铺和个人行数多，完整差异看 --output 文件。
    for change in changes:
        if change["dimension"] == "GROUP":
            print(
                f"  GROUP {change['row']:<22} {change['field']:<32} "
                f"{change['before']} -> {change['after']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="退税Excel数据库工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="初始化全新环境的数据库表（重放冻结的历史建表脚本）")
    for command, label in (
        ("db-status", "查看迁移状态"),
        ("db-baseline", "把现有迁移文件登记为已执行（存量环境只需一次）"),
        ("db-migrate", "执行待执行的迁移"),
    ):
        command_parser = subparsers.add_parser(command, help=label)
        command_parser.add_argument(
            "--target", default="all", choices=["date", "erp", "agent", "all"],
            help="date=Python 数据库，erp=ERP 业务库，agent=AI 助手库",
        )
        if command == "db-baseline":
            command_parser.add_argument(
                "--through", help="只登记文件名不大于该版本的迁移，如 20261028_zzz"
            )
        if command == "db-migrate":
            command_parser.add_argument("--dry-run", action="store_true", help="只列出将执行的迁移")
    refresh_parser = subparsers.add_parser(
        "inventory-sales-refresh",
        help="按页面展示月份回填月度库存快照的销售及关联指标",
    )
    refresh_parser.add_argument(
        "--report-month", required=True, help="页面展示月份，如 2026-10",
    )
    refresh_parser.add_argument(
        "--dry-run", action="store_true", help="只生成回填前后差异，不写库",
    )
    refresh_parser.add_argument("--output", help="把完整差异写入该JSON文件")
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
        bootstrap_legacy_schema()
        print(f"数据库 {settings.mysql_database} 初始化完成")
        return
    if args.command in {"db-status", "db-baseline", "db-migrate"}:
        _run_migration_command(args)
        return
    if args.command == "inventory-sales-refresh":
        _run_inventory_sales_refresh(args)
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
