from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.connections import Connection

from backend.config import settings


def _ensure_customs_declaration_columns(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM customs_declaration_items")
    columns = {row["Field"] for row in cursor.fetchall()}
    if "source_document_key" not in columns:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD COLUMN source_document_key CHAR(64) NULL "
            "COMMENT '合同号+源文件名生成的报关资料标识；同文件重传整份覆盖' "
            "AFTER invoice_no"
        )
        cursor.execute(
            "UPDATE customs_declaration_items SET source_document_key = "
            "SHA2(CONCAT(UPPER(TRIM(contract_no)), '|', "
            "LOWER(TRIM(SUBSTRING_INDEX(REPLACE(uploaded_file_name, '\\\\', '/'), '/', -1)))), 256)"
        )
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "MODIFY COLUMN source_document_key CHAR(64) NOT NULL "
            "COMMENT '合同号+源文件名生成的报关资料标识；同文件重传整份覆盖'"
        )
    if "document_total_usd" not in columns:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD COLUMN document_total_usd DECIMAL(20,4) NULL "
            "COMMENT '该份报关Excel全部商品美元总价；用于匹配回款表报关合同金额' "
            "AFTER source_document_key"
        )
        cursor.execute(
            "UPDATE customs_declaration_items c JOIN ("
            "SELECT source_document_key, SUM(COALESCE(total_price, 0)) AS total_usd "
            "FROM customs_declaration_items GROUP BY source_document_key"
            ") d ON d.source_document_key = c.source_document_key "
            "SET c.document_total_usd = d.total_usd"
        )
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "MODIFY COLUMN document_total_usd DECIMAL(20,4) NOT NULL "
            "COMMENT '该份报关Excel全部商品美元总价；用于匹配回款表报关合同金额'"
        )
    if "customs_match_status" not in columns:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD COLUMN customs_match_status VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED' "
            "COMMENT '18位报关单匹配状态：MATCHED、UNMATCHED或AMBIGUOUS' "
            "AFTER document_total_usd"
        )
    if "customs_declaration_no" not in columns:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD COLUMN customs_declaration_no VARCHAR(30) NULL "
            "COMMENT '预留18位海关编号；当前报关Excel初次上传时为空' "
            "AFTER invoice_no"
        )
    if "declaration_date" not in columns:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD COLUMN declaration_date DATE NULL "
            "COMMENT '预留海关申报日期；当前报关Excel初次上传时为空' "
            "AFTER customs_declaration_no"
        )
    additions = {
        "export_date": (
            "DATE NULL COMMENT '根据合同协议号从外汇回款汇总表自动匹配的出口日期' "
            "AFTER declaration_date"
        ),
        "declaration_month": (
            "CHAR(6) NULL COMMENT '生成出口明细时填写的申报年月，格式YYYYMM；初次上传为空' "
            "AFTER export_date"
        ),
        "declaration_batch": (
            "CHAR(3) NULL COMMENT '生成出口明细时填写的三位申报批次；初次上传为空' "
            "AFTER declaration_month"
        ),
        "sequence_no": (
            "CHAR(8) NULL COMMENT '报关单商品项号补足8位后的申报序号；初次上传为空' "
            "AFTER declaration_batch"
        ),
        "correlation_no": (
            "VARCHAR(50) NULL COMMENT '申报年月+三位申报批次+八位序号；初次上传为空' "
            "AFTER sequence_no"
        ),
        "quantity_value": (
            "DECIMAL(20,6) NULL COMMENT '数量及单位按/拆分后的第一数量，用作出口数量' "
            "AFTER quantity_and_unit"
        ),
        "quantity_unit": (
            "VARCHAR(50) NULL COMMENT '数量及单位按/拆分后的第一单位，用作出口计量单位' "
            "AFTER quantity_value"
        ),
        "second_quantity_value": (
            "DECIMAL(20,6) NULL COMMENT '数量及单位按/拆分后的第二数量，例如法定第二数量或重量' "
            "AFTER quantity_unit"
        ),
        "second_quantity_unit": (
            "VARCHAR(50) NULL COMMENT '数量及单位按/拆分后的第二单位，例如千克' "
            "AFTER second_quantity_value"
        ),
        "unit_price": (
            "DECIMAL(24,12) NULL COMMENT '单价/总价/币制按/拆分后的单价' "
            "AFTER price_total_currency"
        ),
        "total_price": (
            "DECIMAL(20,4) NULL COMMENT '单价/总价/币制按/拆分后的总价，用作美元离岸价' "
            "AFTER unit_price"
        ),
        "currency": (
            "VARCHAR(20) NULL COMMENT '单价/总价/币制按/拆分后的币制，例如USD' "
            "AFTER total_price"
        ),
    }
    for column, definition in additions.items():
        if column not in columns:
            cursor.execute(
                f"ALTER TABLE customs_declaration_items ADD COLUMN {column} {definition}"
            )
    cursor.execute(
        "ALTER TABLE customs_declaration_items "
        "MODIFY COLUMN customs_declaration_no VARCHAR(30) NULL "
        "COMMENT '按合同号及报关总金额匹配的18位海关编号'"
    )
    cursor.execute(
        "ALTER TABLE customs_declaration_items "
        "MODIFY COLUMN declaration_date DATE NULL "
        "COMMENT '预留海关申报日期；当前报关Excel初次上传时为空'"
    )
    cursor.execute(
        "ALTER TABLE customs_declaration_items "
        "MODIFY COLUMN export_date DATE NULL "
        "COMMENT '根据合同协议号从外汇回款汇总表自动匹配的出口日期'"
    )
    cursor.execute("SHOW INDEX FROM customs_declaration_items")
    indexes = {row["Key_name"] for row in cursor.fetchall()}
    if "uk_customs_contract_item" in indexes:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "DROP INDEX uk_customs_contract_item"
        )
    if "uk_customs_document_item" not in indexes:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD UNIQUE INDEX uk_customs_document_item "
            "(source_document_key, item_no)"
        )
    if "uk_customs_declaration_item" not in indexes:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD UNIQUE INDEX uk_customs_declaration_item "
            "(customs_declaration_no, item_no)"
        )
    if "idx_customs_declaration_no" not in indexes:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD INDEX idx_customs_declaration_no (customs_declaration_no)"
        )
    if "idx_customs_correlation_no" not in indexes:
        cursor.execute(
            "ALTER TABLE customs_declaration_items "
            "ADD INDEX idx_customs_correlation_no (correlation_no)"
        )
    cursor.execute(
        "ALTER TABLE customs_declaration_items "
        "MODIFY COLUMN contract_no VARCHAR(100) NOT NULL "
        "COMMENT '报关单页合同协议号；一个合同允许拆分为多份报关资料', "
        "MODIFY COLUMN source_document_key CHAR(64) NOT NULL "
        "COMMENT '合同号+源文件名生成的报关资料标识；同文件重传整份覆盖', "
        "MODIFY COLUMN document_total_usd DECIMAL(20,4) NOT NULL "
        "COMMENT '该份报关Excel全部商品美元总价；用于匹配回款表报关合同金额', "
        "MODIFY COLUMN customs_match_status VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED' "
        "COMMENT '18位报关单匹配状态：MATCHED、UNMATCHED或AMBIGUOUS', "
        "COMMENT = '报关资料商品明细表；同合同多份文件独立保存，匹配后以18位报关单号+项号唯一'"
    )


def _ensure_export_detail_columns(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM tax_refund_export_details LIKE 'export_date'")
    export_date = cursor.fetchone()
    if export_date and export_date["Null"] == "NO":
        cursor.execute(
            "ALTER TABLE tax_refund_export_details "
            "MODIFY COLUMN export_date DATE NULL "
            "COMMENT '出口日期；由报关资料生成时按业务要求暂为空'"
        )


def _ensure_purchase_invoice_summary_indexes(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM purchase_invoice_summary")
    columns = {row["Field"] for row in cursor.fetchall()}
    if "resolved_sku" not in columns:
        cursor.execute(
            "ALTER TABLE purchase_invoice_summary "
            "ADD COLUMN resolved_sku VARCHAR(500) NULL "
            "COMMENT '完整SKU；优先取原始规格型号，原始值为空时按商品行与备注SKU顺序补全' "
            "AFTER specification"
        )
    if "resolved_sku_source" not in columns:
        cursor.execute(
            "ALTER TABLE purchase_invoice_summary "
            "ADD COLUMN resolved_sku_source VARCHAR(30) NOT NULL DEFAULT 'UNRESOLVED' "
            "COMMENT '完整SKU来源：SPECIFICATION原规格、REMARK_ORDERED备注顺序或UNRESOLVED未识别' "
            "AFTER resolved_sku"
        )
    cursor.execute("SHOW INDEX FROM purchase_invoice_summary")
    indexes = {row["Key_name"] for row in cursor.fetchall()}
    if "uk_purchase_summary_year_sequence" in indexes:
        cursor.execute(
            "ALTER TABLE purchase_invoice_summary "
            "DROP INDEX uk_purchase_summary_year_sequence"
        )
    if "idx_purchase_summary_year_sequence" not in indexes:
        cursor.execute(
            "ALTER TABLE purchase_invoice_summary "
            "ADD INDEX idx_purchase_summary_year_sequence "
            "(invoice_year, source_sequence)"
        )
    cursor.execute(
        "ALTER TABLE purchase_invoice_summary "
        "MODIFY COLUMN invoice_year SMALLINT UNSIGNED NOT NULL "
        "COMMENT '采购发票所属年份；从工作表名称或开票日期识别', "
        "MODIFY COLUMN source_sequence INT NOT NULL "
        "COMMENT '来源工作表“序号”，仅用于追溯，不作为增量业务键', "
        "MODIFY COLUMN specification VARCHAR(500) NULL "
        "COMMENT '来源Excel中的原始规格型号', "
        "MODIFY COLUMN goods_or_service_name VARCHAR(1000) NULL "
        "COMMENT '开票品名；已去除星号前的商品大类，例如*发动机*涡轮增压器保存为涡轮增压器', "
        "MODIFY COLUMN resolved_sku VARCHAR(500) NULL "
        "COMMENT '完整SKU；优先取原始规格型号，原始值为空时按商品行与备注SKU顺序补全', "
        "MODIFY COLUMN resolved_sku_source VARCHAR(30) NOT NULL DEFAULT 'UNRESOLVED' "
        "COMMENT '完整SKU来源：SPECIFICATION原规格、REMARK_ORDERED备注顺序或UNRESOLVED未识别', "
        "MODIFY COLUMN source_sheet VARCHAR(100) NOT NULL "
        "COMMENT '数据来源工作表名称', "
        "COMMENT = '采购发票汇总商品明细；读取全部非空工作表并按发票号码整单增量覆盖'"
    )


def _ensure_inventory_match_columns(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM purchase_invoice_inventory")
    columns = {row["Field"] for row in cursor.fetchall()}
    if "inventory_match_type" not in columns:
        cursor.execute(
            "ALTER TABLE purchase_invoice_inventory "
            "ADD COLUMN inventory_match_type VARCHAR(20) NOT NULL DEFAULT 'SKU' "
            "COMMENT '库存匹配类型：SKU精确规格或PRODUCT_NAME通用品名' "
            "AFTER normalized_sku"
        )
    cursor.execute("SHOW INDEX FROM purchase_invoice_inventory")
    indexes = {row["Key_name"] for row in cursor.fetchall()}
    if "idx_inventory_generic_fifo" not in indexes:
        cursor.execute(
            "ALTER TABLE purchase_invoice_inventory "
            "ADD INDEX idx_inventory_generic_fifo "
            "(inventory_match_type, normalized_sku, unit, invoice_date, invoice_no, item_sequence)"
        )
    cursor.execute(
        "ALTER TABLE purchase_invoice_inventory "
        "MODIFY COLUMN specification VARCHAR(500) NOT NULL "
        "COMMENT '库存匹配值；精确库存保存SKU，通用品名库存保存发票品名', "
        "MODIFY COLUMN normalized_sku VARCHAR(500) NOT NULL "
        "COMMENT '去空格并转大写后的库存匹配值', "
        "MODIFY COLUMN inventory_match_type VARCHAR(20) NOT NULL DEFAULT 'SKU' "
        "COMMENT '库存匹配类型：SKU精确规格或PRODUCT_NAME通用品名'"
    )


def _ensure_purchase_detail_fifo_columns(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM tax_refund_purchase_details")
    column_info = {row["Field"]: row for row in cursor.fetchall()}
    columns = set(column_info)
    additions = {
        "detail_key": (
            "VARCHAR(200) NULL COMMENT '进货明细唯一键；MANUAL:关联号或FIFO:出口明细ID:库存批次ID' "
            "AFTER id"
        ),
        "source_type": (
            "VARCHAR(30) NOT NULL DEFAULT 'MANUAL_EXCEL' "
            "COMMENT '数据来源：MANUAL_EXCEL手工Excel或FIFO_INVOICE发票库存分配' "
            "AFTER detail_key"
        ),
        "inventory_allocation_id": (
            "BIGINT UNSIGNED NULL COMMENT 'FIFO生成行对应的库存扣减流水ID；手工Excel行为NULL' "
            "AFTER source_type"
        ),
        "allocation_sequence": (
            "INT NOT NULL DEFAULT 1 COMMENT '同一关联号由多张发票拆分时的FIFO分配顺序，从1开始' "
            "AFTER inventory_allocation_id"
        ),
    }
    for column, definition in additions.items():
        if column not in columns:
            cursor.execute(
                f"ALTER TABLE tax_refund_purchase_details ADD COLUMN {column} {definition}"
            )
    cursor.execute(
        "UPDATE tax_refund_purchase_details "
        "SET detail_key = CONCAT('MANUAL:', correlation_no) "
        "WHERE detail_key IS NULL OR detail_key = ''"
    )
    if "detail_key" not in column_info or column_info["detail_key"]["Null"] == "YES":
        cursor.execute(
            "ALTER TABLE tax_refund_purchase_details MODIFY COLUMN detail_key VARCHAR(200) NOT NULL "
            "COMMENT '进货明细唯一键；MANUAL:关联号或FIFO:出口明细ID:库存批次ID'"
        )
    cursor.execute("SHOW INDEX FROM tax_refund_purchase_details")
    indexes = {row["Key_name"]: int(row["Non_unique"]) for row in cursor.fetchall()}
    if "uk_purchase_correlation_no" in indexes:
        cursor.execute(
            "ALTER TABLE tax_refund_purchase_details DROP INDEX uk_purchase_correlation_no"
        )
    if "uk_purchase_detail_key" not in indexes:
        cursor.execute(
            "ALTER TABLE tax_refund_purchase_details "
            "ADD UNIQUE INDEX uk_purchase_detail_key (detail_key)"
        )
    if "uk_purchase_inventory_allocation" not in indexes:
        cursor.execute(
            "ALTER TABLE tax_refund_purchase_details "
            "ADD UNIQUE INDEX uk_purchase_inventory_allocation (inventory_allocation_id)"
        )
    if "idx_purchase_correlation_no" not in indexes:
        cursor.execute(
            "ALTER TABLE tax_refund_purchase_details "
            "ADD INDEX idx_purchase_correlation_no (correlation_no)"
        )


def _ensure_performance_request_id_columns(cursor) -> None:
    """Keep request IDs large enough for the Java Quartz correlation format."""
    for table_name in (
        "performance_import_batch",
        "performance_refresh_run",
        "scheduler_task_run",
    ):
        cursor.execute(
            f"SHOW COLUMNS FROM `{table_name}` LIKE 'request_id'"
        )
        column = cursor.fetchone()
        if not column:
            cursor.execute(
                f"ALTER TABLE `{table_name}` "
                "ADD COLUMN request_id VARCHAR(128) NULL COMMENT '请求ID'"
            )
            continue
        column_type = str(column.get("Type") or "").lower()
        if column_type.startswith("varchar("):
            try:
                current_length = int(
                    column_type.removeprefix("varchar(").split(")", 1)[0]
                )
            except ValueError:
                current_length = 0
            if current_length >= 128:
                continue
        cursor.execute(
            f"ALTER TABLE `{table_name}` "
            "MODIFY COLUMN request_id VARCHAR(128) NULL COMMENT '请求ID'"
        )


def _connect(database: str | None = None) -> Connection:
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _remove_inventory_report_chengdu_columns(cursor) -> None:
    """移除与本地仓期末在途重复的旧成都仓字段。"""
    for table_name in (
        "monthly_inventory_report_manual_input",
        "dws_inventory_report_department_summary",
    ):
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        if cursor.fetchone() is None:
            continue
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
        existing = {row["Field"] for row in cursor.fetchall()}
        for column in (
            "chengdu_in_transit_total_cost",
            "chengdu_in_transit_qty",
        ):
            if column in existing:
                cursor.execute(
                    f"ALTER TABLE `{table_name}` DROP COLUMN `{column}`"
                )


def _ensure_inventory_report_sales_volume_columns(cursor) -> None:
    """Keep existing inventory-report databases compatible with new fields."""
    definitions = (
        (
            "ods_lingxing_inventory_report_amz_order_profit",
            "volume",
            "DECIMAL(24,6) NOT NULL DEFAULT 0 "
            "COMMENT '自然月商品销量' AFTER `amount`",
        ),
        (
            "dwd_inventory_report_amz_sales_detail",
            "volume",
            "DECIMAL(24,6) NOT NULL DEFAULT 0 "
            "COMMENT '清洗后自然月商品销量' AFTER `amount`",
        ),
        (
            "dws_inventory_report_department_summary",
            "next_month_opening_inventory_qty",
            "DECIMAL(24,6) NULL DEFAULT NULL "
            "COMMENT '次月月初库存数量，取本月海外仓与FBA仓期末库存数量之和' "
            "AFTER `fba_end_in_transit_total_cost`",
        ),
    )
    for table_name, column_name, definition in definitions:
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        if cursor.fetchone() is None:
            continue
        cursor.execute(
            f"SHOW COLUMNS FROM `{table_name}` LIKE %s",
            (column_name,),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                f"ALTER TABLE `{table_name}` "
                f"ADD COLUMN `{column_name}` {definition}"
            )


def _ensure_after_sales_range_columns(cursor) -> None:
    """Add auditable calculation versions without relying on vendor-specific DDL."""
    definitions = (
        (
            "dws_amz_sop_after_sales_summary",
            "calculation_version",
            "VARCHAR(32) NOT NULL DEFAULT 'RECORD-V2' "
            "COMMENT '计算口径版本：QUANTITY-V3按领星售后件数计算' "
            "AFTER `after_sales_rate`",
        ),
        (
            "dws_ebay_sop_after_sales_summary",
            "calculation_version",
            "VARCHAR(32) NOT NULL DEFAULT 'EBAY-QUANTITY-V1' "
            "COMMENT '计算口径版本：保持eBay有效售后数量求和口径' "
            "AFTER `after_sales_rate`",
        ),
    )
    for table_name, column_name, definition in definitions:
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        if cursor.fetchone() is None:
            continue
        cursor.execute(
            f"SHOW COLUMNS FROM `{table_name}` LIKE %s", (column_name,)
        )
        if cursor.fetchone() is None:
            cursor.execute(
                f"ALTER TABLE `{table_name}` "
                f"ADD COLUMN `{column_name}` {definition}"
            )
    cursor.execute(
        "UPDATE dws_amz_sop_after_sales_summary "
        "SET calculation_version=CASE "
        "WHEN sync_batch_id LIKE 'QUANTITY-V3-%%' THEN 'QUANTITY-V3' "
        "ELSE 'RECORD-V2' END "
        "WHERE calculation_version IS NULL OR calculation_version='' "
        "OR calculation_version='LEGACY'"
    )
    cursor.execute(
        "UPDATE dws_ebay_sop_after_sales_summary "
        "SET calculation_version='EBAY-QUANTITY-V1' "
        "WHERE calculation_version IS NULL OR calculation_version='' "
        "OR calculation_version='LEGACY'"
    )


def init_database() -> None:
    database_name = settings.mysql_database.replace("`", "``")
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        connection.commit()
    finally:
        connection.close()

    project_root = Path(__file__).parent.parent
    schema_files = [
        Path(__file__).parent / "schema.sql",
        project_root / "migrations" / "20260807_amz_sop_after_sales.sql",
        project_root / "migrations" / "20260811_ebay_sop_after_sales.sql",
        project_root / "migrations" / "20260812_image_sop.sql",
        project_root / "migrations" / "20260814_inventory_report_source_tables.sql",
        project_root / "migrations" / "20260817_inventory_report_etl_tables.sql",
        project_root / "migrations" / "20260818_ebay_inventory_age_cost.sql",
        project_root / "migrations" / "20260818_inventory_report_purchase_order_transit.sql",
        project_root / "migrations" / "20260819_after_sales_range_optimization.sql",
        project_root / "migrations" / "20260820_inventory_report_dimension_views.sql",
    ]
    schema = "\n".join(
        path.read_text(encoding="utf-8")
        for path in schema_files
        if path.exists()
    )
    connection = _connect(settings.mysql_database)
    try:
        with connection.cursor() as cursor:
            for statement in schema.split(";"):
                if statement.strip():
                    cursor.execute(statement)
            _remove_inventory_report_chengdu_columns(cursor)
            _ensure_inventory_report_sales_volume_columns(cursor)
            _ensure_after_sales_range_columns(cursor)
            _ensure_customs_declaration_columns(cursor)
            _ensure_export_detail_columns(cursor)
            _ensure_purchase_invoice_summary_indexes(cursor)
            _ensure_inventory_match_columns(cursor)
            _ensure_purchase_detail_fifo_columns(cursor)
            _ensure_performance_request_id_columns(cursor)
        connection.commit()
    finally:
        connection.close()


_pool: PooledDB | None = None
_pool_lock = threading.Lock()


def _connection_pool() -> PooledDB:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = PooledDB(
                    creator=pymysql,
                    maxconnections=20,
                    mincached=1,
                    maxcached=10,
                    blocking=True,
                    maxusage=None,
                    ping=1,
                    reset=True,
                    host=settings.mysql_host,
                    port=settings.mysql_port,
                    user=settings.mysql_user,
                    password=settings.mysql_password,
                    database=settings.mysql_database,
                    charset="utf8mb4",
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False,
                )
    return _pool


@contextmanager
def db_connection() -> Iterator[Connection]:
    connection = _connection_pool().connection()
    try:
        yield connection
    finally:
        connection.close()
