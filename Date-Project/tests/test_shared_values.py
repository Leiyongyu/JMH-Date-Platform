from backend.utils.values import text, text_keep_zero


def test_text_treats_falsy_values_as_empty():
    assert text(None) == "" and text(0) == "" and text("  A1 ") == "A1"


def test_text_keep_zero_keeps_numeric_zero():
    assert text_keep_zero(None) == "" and text_keep_zero(0) == "0" and text_keep_zero(" 3 ") == "3"


def test_replenishment_rule_tables_follow_configured_database(monkeypatch):
    from types import SimpleNamespace
    from backend.repositories import ebay_replenishment_v2_repository as repo
    monkeypatch.setattr(repo, "settings", SimpleNamespace(
        ebay_replenishment_rule_database="", shop_source_database="jmh_data_platform"))
    assert repo._rule_database() == "jmh_data_platform"
    monkeypatch.setattr(repo, "settings", SimpleNamespace(
        ebay_replenishment_rule_database="Date-Project", shop_source_database="jmh_data_platform"))
    assert repo._rule_database() == "Date-Project"
    # 共享基础数据（订单、Listing）仍读 ERP 库
    assert repo._source_database() == "jmh_data_platform"
