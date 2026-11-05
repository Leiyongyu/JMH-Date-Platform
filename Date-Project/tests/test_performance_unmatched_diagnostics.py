import unittest
from decimal import Decimal
from unittest.mock import patch

from backend.parsers.performance_common import (
    owner_is_blank,
    owner_is_invisible_whitespace,
)
from backend.repositories import performance_repository as repo
from backend.services import performance_service
from backend.services.performance_service import (
    UNASSIGNED,
    _amazon_match_target,
    _amazon_principal,
    performance_unmatched,
)


class AmazonMatchTargetTest(unittest.TestCase):
    """The key algorithm must stay shared with _amazon_principal."""

    def test_us_store_key_is_the_second_segment(self):
        self.assertEqual(
            _amazon_match_target(
                {"store_name": "US1-嘉茂鸿-US", "local_sku": "ABC-001"}
            ),
            ("STORE", "嘉茂鸿"),
        )

    def test_eu_uk_needs_no_key(self):
        self.assertEqual(
            _amazon_match_target(
                {"store_name": "EU-示例-UK", "local_sku": "ABC-001"}
            ),
            ("EU_UK", ""),
        )

    def test_eu_oth_uses_second_sku_segment(self):
        self.assertEqual(
            _amazon_match_target(
                {"store_name": "EU-示例-DE", "local_sku": "OTH-XY9-001"}
            ),
            ("OTH_CODE", "XY9"),
        )

    def test_eu_other_sku_uses_first_segment(self):
        self.assertEqual(
            _amazon_match_target(
                {"store_name": "EU-示例-DE", "local_sku": "abc-001"}
            ),
            ("BRAND", "ABC"),
        )

    def test_missing_store_name_is_out_of_scope(self):
        self.assertIsNone(_amazon_match_target({"store_name": "", "local_sku": "A-1"}))

    def test_refactor_keeps_principal_behaviour(self):
        rules = {("US1", "STORE", "嘉茂鸿"): "张三"}
        self.assertEqual(
            _amazon_principal(
                {"store_name": "US2-嘉茂鸿-US", "local_sku": "ABC-001"}, rules
            ),
            ("张三", True, False),
        )

    def test_chongqing_alias_still_falls_back(self):
        rules = {("US1", "STORE", "邱存帅"): "邱存帅"}
        self.assertEqual(
            _amazon_principal(
                {"store_name": "US1-重庆茁凯-US", "local_sku": "ABC-001"}, rules
            ),
            ("邱存帅", True, False),
        )


class OwnerCellClassificationTest(unittest.TestCase):
    def test_pending_and_empty_count_as_blank(self):
        for value in ("", "   ", "待定", "待到", None, "nan"):
            self.assertTrue(owner_is_blank(value), value)

    def test_real_name_is_not_blank(self):
        self.assertFalse(owner_is_blank("张三"))

    def test_ideographic_space_is_invisible_whitespace(self):
        self.assertTrue(owner_is_invisible_whitespace("　"))
        self.assertTrue(owner_is_invisible_whitespace("\xa0\xa0"))

    def test_plain_spaces_are_not_flagged(self):
        # MySQL TRIM() handles plain spaces, so those do not diverge.
        self.assertFalse(owner_is_invisible_whitespace("   "))
        self.assertFalse(owner_is_invisible_whitespace("张三"))


class ListRankingsExcludeTest(unittest.TestCase):
    def test_exclude_adds_predicate_and_keeps_table_intact(self):
        captured = {}

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                captured.setdefault("sql", []).append(" ".join(sql.split()))
                captured.setdefault("params", []).append(list(params or []))

            def fetchone(self):
                return {"total": 0}

            def fetchall(self):
                return []

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

        from contextlib import contextmanager

        @contextmanager
        def fake_connection():
            yield FakeConnection()

        with patch.object(repo, "db_connection", fake_connection):
            repo.list_rankings(
                platform="combined",
                stat_month="2026-10",
                principal_name=None,
                order_by="gross_profit",
                order="desc",
                page=1,
                page_size=10,
                exclude_unassigned=True,
            )

        self.assertTrue(
            all("principal_name <> %s" in sql for sql in captured["sql"]),
            captured["sql"],
        )
        # Both the count and the page query must filter identically, or the
        # pagination total would disagree with the rows returned.
        for params in captured["params"]:
            self.assertIn(UNASSIGNED, params)


class UnmatchedDiagnosticsTest(unittest.TestCase):
    def _run(self, profit_rows, rules, raw_rules, ebay_rows=()):
        from contextlib import contextmanager

        @contextmanager
        def fake_connection():
            yield object()

        with patch.object(repo, "latest_ranking_month", return_value="2026-10"), \
             patch.object(repo, "performance_connection", fake_connection), \
             patch.object(repo, "get_amz_profit_rows", return_value=profit_rows), \
             patch.object(repo, "get_owner_rules", return_value=rules), \
             patch.object(repo, "get_owner_rules_raw", return_value=raw_rules), \
             patch.object(repo, "ebay_unmatched_breakdown", return_value=list(ebay_rows)):
            return performance_unmatched("combined", "2026-10")

    def test_store_with_no_rule_row_is_rule_missing(self):
        result = self._run(
            profit_rows=[
                {
                    "store_name": "US1-新店-US",
                    "local_sku": "ABC-001",
                    "gross_profit": Decimal("10"),
                    "net_sales_amount": Decimal("100"),
                }
            ],
            rules={},
            raw_rules={},
        )
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["reason"], "RULE_MISSING")
        self.assertEqual(item["matchKey"], "新店")
        self.assertEqual(item["dimension"], "STORE")
        self.assertEqual(item["sourceRows"], 1)
        self.assertTrue(item["countsInRanking"])

    def test_blank_owner_cell_is_reported_separately(self):
        result = self._run(
            profit_rows=[
                {
                    "store_name": "US1-老店-US",
                    "local_sku": "ABC-001",
                    "gross_profit": Decimal("5"),
                    "net_sales_amount": Decimal("50"),
                }
            ],
            rules={},
            raw_rules={("US1", "STORE", "老店"): "待定"},
        )
        self.assertEqual(result["items"][0]["reason"], "OWNER_BLANK")

    def test_missing_shop_master_data_is_marked_not_counted(self):
        result = self._run(
            profit_rows=[
                {
                    "store_name": "",
                    "local_sku": "ABC-001",
                    "gross_profit": Decimal("7"),
                    "net_sales_amount": Decimal("70"),
                }
            ],
            rules={},
            raw_rules={},
        )
        item = result["items"][0]
        self.assertEqual(item["reason"], "SHOP_UNKNOWN")
        self.assertFalse(item["countsInRanking"])

    def test_matched_rows_and_fixed_uk_owner_are_not_reported(self):
        result = self._run(
            profit_rows=[
                {
                    "store_name": "US1-有主店-US",
                    "local_sku": "ABC-001",
                    "gross_profit": Decimal("1"),
                    "net_sales_amount": Decimal("1"),
                },
                {
                    "store_name": "EU-某店-UK",
                    "local_sku": "ABC-001",
                    "gross_profit": Decimal("2"),
                    "net_sales_amount": Decimal("2"),
                },
            ],
            rules={("US1", "STORE", "有主店"): "李四"},
            raw_rules={("US1", "STORE", "有主店"): "李四"},
        )
        self.assertEqual(result["items"], [])
        self.assertEqual(result["totals"]["keys"], 0)

    def test_same_key_aggregates_rows_and_amounts(self):
        rows = [
            {
                "store_name": "US1-新店-US",
                "local_sku": "ABC-001",
                "gross_profit": Decimal("10"),
                "net_sales_amount": Decimal("100"),
            },
            {
                "store_name": "US2-新店-US",
                "local_sku": "ABC-002",
                "gross_profit": Decimal("20"),
                "net_sales_amount": Decimal("200"),
            },
        ]
        result = self._run(profit_rows=rows, rules={}, raw_rules={})
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["sourceRows"], 2)
        self.assertEqual(result["items"][0]["grossProfit"], "30")
        self.assertEqual(result["totals"]["grossProfit"], "30")

    def test_ebay_whitespace_owner_is_flagged_as_counted_wrongly(self):
        result = self._run(
            profit_rows=[],
            rules={},
            raw_rules={},
            ebay_rows=[
                {
                    "match_key": "XYZ",
                    "reason": "OWNER_WHITESPACE",
                    "source_rows": 3,
                    "gross_profit": Decimal("30"),
                    "net_sales_amount": Decimal("300"),
                    "sample_sku": "XYZ-1",
                }
            ],
        )
        item = result["items"][0]
        self.assertEqual(item["platform"], "ebay")
        self.assertEqual(item["dimension"], "EBAY_BRAND")
        # eBay's SQL accepts the blank-looking cell as a real owner, so the
        # money is NOT in the unassigned bucket - the dialog must say so.
        self.assertFalse(item["countsInRanking"])

    def test_reasons_are_ordered_most_actionable_first(self):
        result = self._run(
            profit_rows=[
                {
                    "store_name": "",
                    "local_sku": "A-1",
                    "gross_profit": Decimal("999"),
                    "net_sales_amount": Decimal("999"),
                },
                {
                    "store_name": "US1-新店-US",
                    "local_sku": "ABC-001",
                    "gross_profit": Decimal("1"),
                    "net_sales_amount": Decimal("1"),
                },
            ],
            rules={},
            raw_rules={},
        )
        # RULE_MISSING outranks SHOP_UNKNOWN even with far less money.
        self.assertEqual(
            [item["reason"] for item in result["items"]],
            ["RULE_MISSING", "SHOP_UNKNOWN"],
        )

    def test_no_month_returns_empty_payload(self):
        with patch.object(repo, "latest_ranking_month", return_value=None):
            result = performance_unmatched("combined", None)
        self.assertIsNone(result["stat_month"])
        self.assertEqual(result["items"], [])
        self.assertEqual(result["totals"]["keys"], 0)


if __name__ == "__main__":
    unittest.main()
