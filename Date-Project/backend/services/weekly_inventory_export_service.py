from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from backend.config import settings
from backend.services.weekly_inventory_sync_service import number

BASE_COLUMNS = [("仓库名称", "warehouse_name"), ("SKU", "sku"), ("产品名称", "product_name"),
                ("本地产品id", "product_id"), ("实际库存总量", "product_total"), ("可用量", "product_valid_num"),
                ("次品量", "product_bad_num"), ("待检待上架量", "product_qc_num"), ("锁定量", "product_lock_num")]
SPEC_COLUMNS = [(f"采购-{label}规格-{direction}(CM)", f"cg_{key}_{axis}")
                for label, key in (("产品", "product"), ("包装", "package"), ("外箱", "box"))
                for direction, axis in (("长", "length"), ("宽", "width"), ("高", "height"))]
SPEC_COLUMNS += [("采购-产品净重(G)", "cg_product_net_weight"), ("采购-产品毛重(G)", "cg_product_gross_weight"),
                 ("采购-外箱实重(KG)", "cg_box_weight")]


def export_root():
    return (Path(settings.export_output_dir) / "weekly_inventory").resolve()


def download_path(record):
    if not record or record["status"] != "SUCCESS":
        raise FileNotFoundError("周报不存在或尚未生成成功")
    path = Path(record["file_path"]).resolve()
    if not path.is_relative_to(export_root()) or path.name != record["file_name"] or path.suffix.lower() != ".xlsx":
        raise ValueError("周报文件路径不合法")
    if not path.is_file():
        raise FileNotFoundError("留底文件缺失，请联系管理员检查磁盘")
    return path


def build_rows(groups, names):
    # Select an entire representative row, not independent MAXs. Its seller's
    # buckets and third-party inventory must follow the same representative.
    inventory = {}
    def rank(row):
        qty = number(row.get("product_total"))
        return (qty is not None, qty if qty is not None else Decimal(0), str(row.get("seller_id") or "0"))
    for row in groups["inventory"]:
        key = (row["wid"], row["product_id"])
        previous = inventory.get(key)
        if previous and previous.get("sku") != row.get("sku"):
            raise ValueError("同仓同产品ID对应多个SKU，拒绝不确定的合并")
        if previous is None or rank(row) > rank(previous):
            inventory[key] = row
    products = {row["product_id"]: row for row in groups["products"]}
    bins = defaultdict(list)
    for row in groups["bins"]:
        bins[(row["wid"], row["product_id"])].append(row)
    ages, label_order = {}, {}
    for row in groups["age"]:
        key = (row["wid"], row["product_id"], str(row["seller_id"]))
        ages.setdefault(key, {})[row["bucket_name"]] = row["qty"]
        label_order[row["bucket_name"]] = min(label_order.get(row["bucket_name"], row["bucket_index"]), row["bucket_index"])
    labels = sorted(label_order, key=lambda name: (label_order[name], name))
    headers = [label for label, _ in BASE_COLUMNS] + labels + ["锁定量(仓位)", "未锁定量(仓位)"]
    headers += [f"第三方-{name}-{field}" for name in ("可用量", "调拨在途", "锁定量") for field in ("系统", "三方仓", "差异")]
    headers += [label for label, _ in SPEC_COLUMNS] + ["采购单价", "库存金额"]
    output = []
    for key, source in sorted(inventory.items(), key=lambda pair: (str(names.get(pair[0][0]) or ""), str(pair[1].get("sku") or ""), pair[0])):
        product = products.get(source["product_id"], {})
        bin_rows = bins[key]
        row = {**source, "warehouse_name": names.get(source["wid"]) or next((b.get("wh_name") for b in bin_rows if b.get("wh_name")), None),
               "product_name": product.get("product_name") or next((b.get("product_name") for b in bin_rows if b.get("product_name")), None)}
        if not row["warehouse_name"]:
            raise ValueError(f"仓库 {source['wid']} 缺少名称，请先同步仓库字典")
        values = [row.get(field) for _, field in BASE_COLUMNS]
        buckets = ages.get((*key, str(source["seller_id"])), {})
        values += [buckets.get(label) for label in labels]
        for field in ("lock_num", "valid_num"):
            quantities = [number(b.get(field)) for b in bin_rows]
            values.append(sum(quantities, Decimal(0)) if quantities and all(q is not None for q in quantities) else None)
        third = source.get("third_inventory") or {}
        if isinstance(third, str):
            third = json.loads(third)
        third_by_name = {item["name"]: item for item in third.get("third_inventory_data") or []}
        values += [number(third_by_name.get(name, {}).get(field)) for name in ("可用量", "调拨在途", "锁定量") for field in ("local", "third", "diff")]
        values += [product.get(field) for _, field in SPEC_COLUMNS]
        price, qty = number(source.get("purchase_price")), number(source.get("product_total"))
        values += [price, price * qty if price is not None and qty is not None else None]
        output.append(values)
    return headers, output


def write_export(groups, names, path: Path):
    headers, rows = build_rows(groups, names)
    if not rows:
        raise ValueError("没有可导出的周报数据")
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("仓位库存明细")
    sheet.freeze_panes = "E2"
    def safe(values):
        cells = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                cell.data_type = "s"  # Never execute an imported SKU/name as a formula.
            if isinstance(value, Decimal):
                cell.number_format = "0.######"
            cells.append(cell)
        return cells
    sheet.append(safe(headers))
    for row in rows:
        sheet.append(safe(row))
    fd, temporary = tempfile.mkstemp(prefix=".weekly-", suffix=".xlsx", dir=path.parent)
    os.close(fd)
    try:
        workbook.save(temporary)
        with open(temporary, "r+b") as stream:
            os.fsync(stream.fileno())
        # Exclusive atomic publication, on the same volume; never replace archives.
        os.link(temporary, path)
    finally:
        workbook.close()
        Path(temporary).unlink(missing_ok=True)
    return {"row_count": len(rows), "column_count": len(headers), "file_size": path.stat().st_size}
