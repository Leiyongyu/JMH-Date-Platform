import json
from pathlib import Path
import pytest


@pytest.fixture
def level_rows():
    return json.loads((Path(__file__).parent / 'fixtures/ebay_level_rules.json').read_text(encoding='utf-8'))


@pytest.fixture
def level_rules(level_rows):
    from backend.services.ebay_level_rule_service import prepare_levels
    return prepare_levels(level_rows)


_MYSQL_OPT_IN = ("RUN_MIXED_PRICE_MYSQL_TESTS", "RUN_REPLENISHMENT_MYSQL_TESTS")


@pytest.fixture(autouse=True)
def _forbid_real_mysql(monkeypatch):
    """单元测试禁止连接真实 MySQL；需要真库的集成测试用 RUN_*_MYSQL_TESTS=1 显式开启。

    否则漏 mock 的测试在开发机上会悄悄读写本地库，在 CI 上又会因为没有库而失败。
    """
    import os
    if any(os.getenv(name) == "1" for name in _MYSQL_OPT_IN):
        return

    def refuse(*args, **kwargs):
        raise AssertionError("单元测试不能连接真实 MySQL，请 mock 对应的 repository")

    import pymysql
    from backend import database
    monkeypatch.setattr(pymysql, "connect", refuse)
    monkeypatch.setattr(database, "_pools", {})
    monkeypatch.setattr(database, "_connection_pool", refuse)
