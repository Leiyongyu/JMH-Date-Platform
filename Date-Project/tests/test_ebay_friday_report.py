"""eBay 周五数据：还原《有货无货检查》Excel 的规则；数据库全部 mock。"""
from datetime import date

import pytest

from backend.services import ebay_friday_report_service as service

TODAY = date(2026, 11, 13)
STORES = [
    {"store_key": "autoteilefastship", "store_name": "autoteilefastship", "main_site": "UK", "sort_order": 30},
    {"store_key": "piecessaleshop", "store_name": "pieces_saleshop", "main_site": "DE", "sort_order": 10},
    {"store_key": "zerozerozone", "store_name": "zero_zero_zone", "main_site": "US", "sort_order": 50},
]
RULES = [{"match_key": "BMW", "principal_name": "房伟", "rule_type": "EBAY_BRAND"},
         {"match_key": "MCD", "principal_name": "杨萍", "rule_type": "EBAY_BRAND"}]


def listing(item, sku, account, site, qty=5, sold=None, start="2026-11-01T08:00:00.000Z"):
    return {"item_id": item, "sku": sku, "seller_account": account, "site": site, "quantity_available": qty,
            "quantity_sold": sold, "start_time": start}


def stock(sku, code, sellable, **extra):
    return {"warehouse_code": code, "warehouse_desc": code, "product_sku": sku, "product_title": "手刹控制模块",
            "sellable": sellable, "reserved": 0, "onway": 16, "transfer_onway": 0, "total_onway": 16,
            "unsellable": 0, "pi_freeze": 0, "pi_warning_qty": 0, "product_type": 0,
            "raw_json": {"product_barcode": "G10645-" + sku, "shipped": "62", "product_freeze_status_text": "正常",
                         **extra}}


def build(listings, stocks, sources=("BMW-30002-0002", "MCD-20022-0001")):
    return service.build(listings, stocks, STORES, RULES, list(sources), TODAY)


@pytest.mark.parametrize("raw,site", [("UK", "UK"), ("US", "US"), ("eBayMotors", "US"), ("DE", "DE"),
                                      ("FR", "DE"), ("", "DE")])
def test_listing_site_follows_the_excel_formula(raw, site):
    assert service.listing_site(raw) == site


@pytest.mark.parametrize("code,site", [("UK", "UK"), ("USEA", "US"), ("USWE", "US"), ("USCE", "US"),
                                       ("DE", "DE"), ("CZ", "DE")])
def test_warehouse_site_follows_the_excel_formula(code, site):
    assert service.warehouse_site(code) == site


def test_used_sku_and_store_key():
    assert service.is_used("DAS-10600-0557-YXR") and service.is_used("FRD-70013-0082-RXY")
    assert service.is_used("JMH-30020-2-0018-YXQ") and not service.is_used("BMW-30002-0001")
    assert service.is_used("FCA-50087-0135-QXY") and service.is_used("BMW-30020-0018-YXR+BMW")
    assert service.is_used("MCD-20034-0010-YXR/XY")
    assert service.brand_mid("2PC-OTH-230681-1247") == ("OTH", "230681"), "多件装前缀不当品牌"
    assert service.brand_mid("4PC-DAS-10254-0040") == ("DAS", "10254")
    assert service.brand_mid("BMW-30002-0001") == ("BMW", "30002")
    assert service.store_key("autoteile-fast-ship") == service.store_key("autoteilefastship")
    assert service.store_key("zero-zero-zone") == service.store_key("zero_zero_zone")


def test_mid_code_brand_prefers_the_brand_with_most_skus():
    mapping = service.mid_brand_map(["BMW-30002-0001", "BMW-30002-0002", "MIN-30002-0003", "JMH-40001-0001"])
    assert mapping == {"30002": "BMW"}, "JMH 前缀不参与推导"


def test_overseas_stock_is_summed_by_mid_code_site_and_used():
    listings, _ = build(
        [listing("1", "BMW-30002-0001", "autoteile-fast-ship", "UK"),
         listing("2", "BMW-30002-0001-YXR", "autoteile-fast-ship", "UK")],
        [stock("JMH-30002-0001", "UK", 31), stock("JMH-30002-0009", "UK", 4),
         stock("JMH-30002-0001-YXR", "UK", 2), stock("JMH-30002-0001", "DE", 50)])
    new, used = listings
    assert new["overseas_stock"] == 35, "同一中间码不同尾号合并（与 Excel SUMIFS 一致），不含二手和其他站点"
    assert used["overseas_stock"] == 2 and used["is_used"] == 1


def test_listing_row_fields_and_judge():
    listings, _ = build(
        [listing("198776706551", "BMW-30002-0001", "autoteile-fast-ship", "UK", qty=14, sold=None,
                 start="2026-11-06T08:24:19.000Z"),
         listing("880110897824", "MCD-20022-0024", "pieces_saleshop", "UK", qty=3, sold=7),
         listing("9", "BMW-30002-0001", "unknown-store", "DE")],
        [stock("JMH-30002-0001", "UK", 14)])
    ok, wrong, unknown = listings
    assert ok["store_name"] == "autoteilefastship", "店铺名按主站点表显示，写法差异已归一"
    assert (ok["site"], ok["plan_site"], ok["site_match"]) == ("UK", "UK", 1)
    assert ok["sold_qty"] == 0, "eBay 不返回售出数按 0"
    assert ok["start_time"].strftime("%Y-%m-%d %H:%M:%S") == "2026-11-06 16:24:19", "UTC 换北京时间"
    assert (ok["brand"], ok["mid_code"], ok["principal_name"]) == ("BMW", "30002", "房伟")
    assert (wrong["site"], wrong["plan_site"], wrong["site_match"]) == ("UK", "DE", 0)
    assert unknown["plan_site"] is None and unknown["site_match"] is None


def test_stock_rows_store_columns_and_no_link():
    listings, stocks = build(
        [listing("111", "BMW-30002-0001", "autoteile-fast-ship", "UK", start="2026-11-02T00:00:00Z"),
         listing("222", "BMW-30002-0001", "pieces_saleshop", "UK", sold=5, start="2026-11-03T00:00:00Z"),
         listing("333", "BMW-30002-0001", "autoteile-fast-ship", "UK", start="2026-11-04T00:00:00Z"),
         listing("444", "BMW-30002-0001", "pieces_saleshop", "DE")],
        [stock("JMH-30002-0001", "UK", 31), stock("JMH-20022-0024", "DE", 3), stock("JMH-99999-0001", "UK", 1)])
    linked, unlinked, no_brand = stocks
    assert linked["sku"] == "BMW-30002-0001" and linked["brand"] == "BMW" and linked["principal_name"] == "房伟"
    assert linked["site"] == "UK" and linked["shipped"] == 62 and linked["product_barcode"] == "G10645-JMH-30002-0001"
    assert linked["store_items_json"] == {"autoteilefastship": "333、111", "piecessaleshop": "222:5"}, \
        "同站点同 SKU 的 Item，新上架在前；挂在主站点不符店铺上的写成 Item:历史售出；其他站点的不算"
    assert linked["no_link"] == 0
    assert unlinked["sku"] == "MCD-20022-0024" and unlinked["no_link"] == 1 and unlinked["store_items_json"] == {}
    assert no_brand["brand"] is None and no_brand["sku"] == "JMH-99999-0001" and no_brand["principal_name"] is None
    summary = service.summarize(listings, stocks)
    assert summary["stock_no_link"] == 2 and summary["stock_no_brand"] == 1 and summary["site_mismatch"] == 1


def test_generate_refuses_empty_upstream(monkeypatch):
    monkeypatch.setattr(service.repo, "latest_listings", lambda: ([], {}))
    monkeypatch.setattr(service.repo, "goodcang_stock", lambda: ([stock("JMH-1-1", "UK", 1)], None))
    monkeypatch.setattr(service.repo, "stores", lambda: STORES)
    with pytest.raises(service.EbayFridayReportError, match="eBay 在售刊登"):
        service.generate(TODAY)


def test_generate_writes_one_snapshot(monkeypatch):
    saved = {}
    monkeypatch.setattr(service.repo, "latest_listings", lambda: (
        [listing("1", "BMW-30002-0001", "autoteile-fast-ship", "UK")], {"stat_month": "2026-11", "pulled_at": None}))
    monkeypatch.setattr(service.repo, "goodcang_stock", lambda: ([stock("JMH-30002-0001", "UK", 3)], None))
    monkeypatch.setattr(service.repo, "stores", lambda: STORES)
    monkeypatch.setattr(service.repo, "ebay_owner_rules", lambda month: saved.setdefault("month", month) and RULES)
    monkeypatch.setattr(service.repo, "brand_sku_sources", lambda: ["BMW-30002-0001"])
    monkeypatch.setattr(service.repo, "replace_report", lambda run, l, s: saved.update(run=run, l=l, s=s))
    result = service.generate(TODAY, operator="admin")
    assert saved["month"] == "2026-11" and saved["run"]["generated_by"] == "admin"
    assert [c["key"] for c in saved["run"]["store_columns"]] == ["autoteilefastship", "piecessaleshop", "zerozerozone"]
    assert result["listing_count"] == 1 and result["stock_rows"] == 1 and result["ods_rows"] == 2


def test_task_is_registered_under_the_listing_lock():
    from backend.services import scheduler_service
    spec = scheduler_service.TASK_SPECS[service.TASK_CODE]
    assert spec.lock_name(None) == "ebay:store-listing:replace"
    assert service.EbayFridayReportError in scheduler_service._STAGED_ERRORS


def test_store_main_site_validation(monkeypatch):
    saved = []
    monkeypatch.setattr(service.repo, "upsert_store", saved.append)
    monkeypatch.setattr(service.repo, "delete_store", lambda key: saved.append(("delete", key)) or 1)
    with pytest.raises(ValueError, match="DE、UK、US"):
        service.save_store({"store_name": "AutoBoss", "main_site": "FR"}, "admin")
    service.save_store({"store_name": "Auto-Boss", "main_site": "us", "original_key": "autobossold"}, "admin")
    assert saved[0] == ("delete", "autobossold")
    assert saved[1]["store_key"] == "autoboss" and saved[1]["main_site"] == "US" and saved[1]["updated_by"] == "admin"


def test_migration_is_ascii_and_seeds_forty_stores():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "migrations" / "20261113_ebay_friday_report.sql").read_text("ascii")
    assert text.startswith("-- Target DB") and "USE `date-project`;" in text and "SET NAMES utf8mb4;" in text
    seed = text[text.index("INSERT IGNORE INTO `ebay_store_main_site`"):text.index("CREATE TABLE IF NOT EXISTS `ebay_friday_report_run`")]
    assert seed.count("'SYSTEM')") == 40
    assert "('autoteilefastship','autoteilefastship','UK'" in seed


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.calls.append(params)

    def executemany(self, sql, rows):
        self.calls.extend(rows)


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def begin(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def cursor(self):
        return self._cursor


def test_replace_report_binds_store_items_as_json_text(monkeypatch):
    """回归：店铺列是 dict，直接交给 pymysql 会报 dict can not be used as parameter（首次本机生成实测）。"""
    from backend.repositories import ebay_friday_report_repository as repo
    cursor = _Cursor()
    monkeypatch.setattr(repo, "db_connection", lambda: _Connection(cursor))
    stock_row = {column: None for column in repo.STOCK_COLUMNS}
    stock_row.update(report_date=TODAY, row_no=1, product_sku="JMH-1", store_items_json={"autoboss": "1、2:3"})
    repo.replace_report({"report_date": TODAY, "generated_at": TODAY}, [], [stock_row])
    bound = [value for call in cursor.calls if call for value in call]
    assert '{"autoboss": "1、2:3"}' in bound
    assert not any(isinstance(value, dict) for value in bound)


def test_replace_report_keeps_only_the_latest_issue(monkeypatch):
    """不留历史：生成新一期前清空三张表（不按日期删），失败时整体回滚。"""
    from backend.repositories import ebay_friday_report_repository as repo
    statements = []

    class Cursor(_Cursor):
        def execute(self, sql, params=None):
            statements.append(" ".join(sql.split()))

    monkeypatch.setattr(repo, "db_connection", lambda: _Connection(Cursor()))
    repo.replace_report({"report_date": TODAY, "generated_at": TODAY}, [], [])
    deletes = [s for s in statements if s.startswith("DELETE")]
    assert deletes == [f"DELETE FROM `{t}`" for t in (repo.LISTING_TABLE, repo.STOCK_TABLE, repo.RUN_TABLE)]
