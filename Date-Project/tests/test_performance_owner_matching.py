import unittest
from decimal import Decimal
from unittest.mock import patch

from backend.services import performance_service
from backend.services.performance_service import (
    UNASSIGNED,
    _amazon_principal,
    _amazon_store_rules,
    _refresh_amazon,
)


class AmazonOwnerMatchingTest(unittest.TestCase):
    def test_store_rule_ignores_store_group_prefix(self):
        rules = {("US1", "STORE", "吉西瑞雅"): "赵昕怡"}

        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "US3-吉西瑞雅-US",
                    "local_sku": "ABC-001",
                },
                rules,
            ),
            ("赵昕怡", True, False),
        )

    def test_unconfigured_amazon_store_is_unassigned_not_excluded(self):
        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "US9-未知店铺-US",
                    "local_sku": "ABC-001",
                },
                {},
            ),
            (UNASSIGNED, True, False),
        )

    def test_eu_brand_rule_remains_available_as_fallback(self):
        rules = {("EU", "BRAND", "ABC"): "负责人A"}

        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "EU-示例店铺-DE",
                    "local_sku": "ABC-001",
                },
                rules,
            ),
            ("负责人A", True, False),
        )

    def test_eu_uk_site_always_uses_fixed_owner(self):
        rules = {("EU", "BRAND", "ABC"): "其他品牌负责人"}

        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "EU-示例店铺-uk",
                    "local_sku": "ABC-001",
                },
                rules,
            ),
            ("吴清栩", True, False),
        )

    def test_eu_store_dimension_does_not_leak_into_us_store_matching(self):
        rules = {
            ("EU", "STORE", "同名店铺"): "EU店铺负责人",
            ("US1", "STORE", "同名店铺"): "US店铺负责人",
        }

        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "US2-同名店铺-US",
                    "local_sku": "ABC-001",
                },
                rules,
            ),
            ("US店铺负责人", True, False),
        )

    def test_eu_keeps_original_brand_logic_even_with_store_rule(self):
        rules = {
            ("EU", "BRAND", "ABC"): "品牌负责人",
            ("US1", "STORE", "示例店铺"): "店铺负责人",
        }

        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "EU-示例店铺-DE",
                    "local_sku": "ABC-001",
                },
                rules,
            ),
            ("品牌负责人", True, False),
        )

    def test_conflicting_store_owners_are_rejected(self):
        rules = {
            ("US1", "STORE", "同名店铺"): "负责人A",
            ("US2", "STORE", "同名店铺"): "负责人B",
        }

        with self.assertRaisesRegex(ValueError, "店铺负责人配置冲突"):
            _amazon_store_rules(rules)

    def test_chongqing_store_prefers_exact_current_month_rule(self):
        rules = {
            ("US1", "STORE", "重庆茁凯"): "袁巾茹",
            ("US1", "STORE", "邱存帅"): "旧负责人",
        }

        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "US1-重庆茁凯-US",
                    "local_sku": "ABC-001",
                },
                rules,
            ),
            ("袁巾茹", True, False),
        )

    def test_chongqing_store_keeps_legacy_alias_as_fallback(self):
        rules = {("US1", "STORE", "邱存帅"): "袁巾茹"}

        self.assertEqual(
            _amazon_principal(
                {
                    "store_name": "US1-重庆茁凯-US",
                    "local_sku": "ABC-001",
                },
                rules,
            ),
            ("袁巾茹", True, False),
        )

    @patch.object(performance_service.repo, "replace_amz_ranking")
    @patch.object(performance_service.repo, "get_owner_rules")
    @patch.object(performance_service.repo, "get_amz_profit_rows")
    def test_amz_refresh_keeps_totals_and_persists_per_owner_matched_rows(
        self, get_profit_rows, get_owner_rules, replace_ranking
    ):
        get_owner_rules.return_value = {
            ("US1", "STORE", "重庆茁凯"): "袁巾茹",
            ("US1", "STORE", "邱存帅"): "旧负责人",
        }
        get_profit_rows.return_value = [
            {
                "store_name": "US1-重庆茁凯-US",
                "local_sku": "ABC-001",
                "gross_profit": Decimal("2.00"),
                "amount": Decimal("10.00"),
                "refund_amount": Decimal("-1.00"),
            },
            {
                "store_name": "US1-重庆茁凯-CA",
                "local_sku": "ABC-002",
                "gross_profit": Decimal("3.00"),
                "amount": Decimal("20.00"),
                "refund_amount": Decimal("-2.00"),
            },
            {
                "store_name": "US1-未配置店铺-US",
                "local_sku": "ABC-003",
                "gross_profit": Decimal("-1.00"),
                "amount": Decimal("5.00"),
                "refund_amount": Decimal("0.00"),
            },
        ]

        result = _refresh_amazon(object(), "2026-08")

        rows = replace_ranking.call_args.args[2]
        by_owner = {row["principal_name"]: row for row in rows}
        owner_row = by_owner["袁巾茹"]
        unassigned_row = by_owner[UNASSIGNED]
        self.assertEqual(owner_row["source_rows"], 2)
        self.assertEqual(owner_row["matched_rows"], 2)
        self.assertEqual(unassigned_row["source_rows"], 1)
        self.assertEqual(unassigned_row["matched_rows"], 0)
        self.assertEqual(unassigned_row["unmatched_rows"], 1)
        self.assertEqual(
            sum((row["gross_profit"] for row in rows), Decimal("0")),
            Decimal("4.00"),
        )
        self.assertEqual(
            sum((row["amount"] for row in rows), Decimal("0")),
            Decimal("35.00"),
        )
        self.assertEqual(
            sum((row["refund_amount"] for row in rows), Decimal("0")),
            Decimal("-3.00"),
        )
        self.assertEqual(result["matched_rows"], 2)
        self.assertEqual(result["unmatched_rows"], 1)


if __name__ == "__main__":
    unittest.main()
