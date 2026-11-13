"""eBay 周五数据 / 订单售出统计：还原《订单售出数统计》「透视」；数据库全部 mock。"""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.services import ebay_friday_order_sales_service as service

HEADERS = ["平台订单号", "发货状态", "付款时间", "平台", "币种", "库存SKU", "购买数量", "汇率", "收入", "国家中文"]
RULES = [{"match_key": "DAS", "principal_name": "方黎力", "rule_type": "EBAY_BRAND"},
         {"match_key": "MCD", "principal_name": "杨萍", "rule_type": "EBAY_BRAND"}]


def workbook(rows, headers=HEADERS):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def order(no, sku, currency="EUR", rate=7.44217, income=100, qty=1, platform="eBay", status="已发货",
          pay="2026-11-12 23:37:11"):
    return [no, status, pay, platform, currency, sku, qty, rate, income, "德国"]


def test_currency_site_follows_the_excel_formula():
    assert service.currency_site("USD") == "US"
    assert service.currency_site("EUR") == "DE"
    assert service.currency_site("GBP") == "UK" and service.currency_site("") == "UK"


def test_parse_keeps_ebay_rows_with_sku_and_counts_the_rest():
    content = workbook([
        order("1", "DAS-10174-0036", currency="GBP", rate=8.89721, income=183.33),
        order("2", "2PC-MCD-20503-0557", qty=2),
        order("3", "JMH-10388-0264", currency="USD", rate=6.6751),
        order("4", "MCD-20425-0557", platform="Walmart", currency="USD"),
        order("5", None),
        order("6", "DAS-10032-0119-YXR", status="已作废,已退款"),
    ])
    lines, stats = service.parse(content, {"10388": "DAS"})
    assert [line["order_no"] for line in lines] == ["1", "2", "3", "6"], "作废 / 退款订单照原表一起算"
    assert stats["source_rows"] == 6 and stats["used_rows"] == 4
    assert stats["excluded"] == {"非 eBay 平台（Walmart）": 1, "库存SKU 为空": 1}
    assert (lines[0]["brand"], lines[0]["mid_code"], lines[0]["site"]) == ("DAS", "10174", "UK")
    assert (lines[1]["brand"], lines[1]["mid_code"], lines[1]["quantity"]) == ("MCD", "20503", 2), "多件装前缀不当品牌"
    assert (lines[2]["brand"], lines[2]["site"]) == ("DAS", "US"), "JMH 开头按中间码推品牌"
    assert lines[0]["pay_time"] == datetime(2026, 11, 12, 23, 37, 11)
    assert lines[0]["order_rate"] == Decimal("8.89721") and lines[0]["income"] == Decimal("183.33")


def test_parse_rejects_wrong_files():
    with pytest.raises(ValueError, match="缺少列"):
        service.parse(workbook([["x"]], headers=["平台订单号", "平台"]), {})
    with pytest.raises(ValueError, match="没有 eBay"):
        service.parse(workbook([order("1", "DAS-1-1", platform="Walmart")]), {})
    with pytest.raises(ValueError, match="无法读取"):
        service.parse(b"not an excel file", {})


def test_usd_rate_falls_back_to_the_latest_published_month():
    rates = {"2026-09": Decimal("6.7787"), "2026-10": Decimal("6.7138")}
    assert service.rate_for("2026-11", rates) == ("2026-10", Decimal("6.7138")), "11 月未出用 10 月"
    assert service.rate_for("2026-09", rates) == ("2026-09", Decimal("6.7787"))
    assert service.rate_for("2026-01", rates) is None


def line(sku, mid, site, income, rate, qty=1, brand=None, pay=datetime(2026, 11, 10)):
    return {"stock_sku": sku, "brand": brand or sku.split("-")[0], "mid_code": mid, "site": site,
            "income": Decimal(str(income)), "order_rate": Decimal(str(rate)), "quantity": qty, "pay_time": pay}


def test_pivot_distinct_mid_site_usd_and_quantity_per_owner():
    lines = [
        line("DAS-10174-0036", "10174", "UK", 183.33, 8.89721),
        line("DAS-10174-0099", "10174", "UK", 10, 8.89721, qty=2),
        line("DAS-10174-0036", "10174", "DE", 50, 7.44217),
        line("MCD-20503-0557", "20503", "DE", 164.04, 7.44217, qty=3),
        line("ZZZ-1-1", "1", "US", 5, 6.6751),
    ]
    result = service.pivot(lines, RULES, {"2026-10": Decimal("6.70341")})
    rows = {r["principal_name"]: r for r in result["rows"]}
    das = rows["方黎力"]
    assert das["distinct_mid_site"] == 2, "同一中间码+站点只计一次，不同站点分开"
    assert das["quantity"] == 4
    expected = (Decimal("183.33") * Decimal("8.89721") + Decimal(10) * Decimal("8.89721")
                + Decimal(50) * Decimal("7.44217")) / Decimal("6.70341")
    assert das["usd_income"] == str(expected.quantize(Decimal("0.01")))
    assert rows["杨萍"]["distinct_mid_site"] == 1 and rows["杨萍"]["quantity"] == 3
    assert result["rows"][-1]["principal_name"] == "未分配", "未分配排最后"
    assert result["total"]["distinct_mid_site"] == 4 and result["total"]["quantity"] == 8
    assert result["usd_rate_months"] == {"2026-11": {"rate_month": "2026-10", "rate": "6.70341"}}


def test_pivot_reports_lines_without_any_usd_rate():
    result = service.pivot([line("DAS-1-1", "1", "DE", 10, 7.4)], RULES, {})
    assert result["missing_rate_lines"] == 1 and result["total"]["usd_income"] == "0.00"


class _Cursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.log.append(" ".join(sql.split())[:40])

    def executemany(self, sql, rows):
        self.log.append(("many", len(rows)))


class _Connection:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def begin(self):
        pass

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")

    def cursor(self):
        return _Cursor(self.log)


def test_import_replaces_the_previous_upload(monkeypatch):
    log = []
    monkeypatch.setattr(service, "db_connection", lambda: _Connection(log))
    monkeypatch.setattr(service.friday.repo, "brand_sku_sources", lambda: [])
    result = service.import_orders(workbook([order("1", "DAS-10174-0036"), order("2", "MCD-1-1")]), "a.xlsx", "admin")
    assert log[:2] == ["DELETE FROM `ebay_friday_order_line`", "DELETE FROM `ebay_friday_order_upload`"], "不留历史"
    assert ("many", 2) in log and log[-1] == "commit"
    assert result["used_rows"] == 2


def test_migration_is_ascii_with_use_and_set_names():
    text = (Path(__file__).resolve().parents[1] / "migrations" / "20261113_ebay_friday_order_sales.sql").read_text("ascii")
    assert "USE `date-project`;" in text and "SET NAMES utf8mb4;" in text
    assert "`ebay_friday_order_upload`" in text and "`ebay_friday_order_line`" in text


def test_import_endpoint_accepts_a_multipart_upload(monkeypatch):
    """端到端的 Python 一段：Java 以 multipart 转发文件，接口按 file 字段收、带上操作人。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.deps import require_internal_access
    from backend.api.v1 import ebay_friday_report as api

    seen = {}
    monkeypatch.setattr(api.order_sales, "import_orders",
                        lambda content, filename, operator: seen.update(size=len(content), name=filename, op=operator)
                        or {"used_rows": 2})
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_internal_access] = lambda: None
    content = workbook([order("1", "DAS-10174-0036")])
    with TestClient(app) as client:
        ok = client.post("/api/v1/finance/ebay-friday-report/order-sales/import", params={"operator": "admin"},
                         files={"file": ("订单.xlsx", content,
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert ok.status_code == 200 and ok.json()["data"]["used_rows"] == 2
        assert seen == {"size": len(content), "name": "订单.xlsx", "op": "admin"}
        not_multipart = client.post("/api/v1/finance/ebay-friday-report/order-sales/import", json={"file": "x"})
        assert not_multipart.status_code == 422, "不是 multipart 时直接拒绝，不会当成空文件导入"
