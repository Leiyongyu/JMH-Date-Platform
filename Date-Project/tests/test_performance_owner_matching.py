import unittest

from backend.services.performance_service import (
    UNASSIGNED,
    _amazon_principal,
    _amazon_store_rules,
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


if __name__ == "__main__":
    unittest.main()
