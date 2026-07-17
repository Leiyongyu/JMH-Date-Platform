import unittest

from modules.tax_refund.parsers.sku_normalizer import normalize_sku


class NormalizeSkuTests(unittest.TestCase):
    def test_accepts_structured_numeric_skus_from_customs_workbook(self):
        for raw_sku in (
            "50113-0112",
            "180014-0206",
            "10169-0061",
            "180013-0206",
        ):
            with self.subTest(raw_sku=raw_sku):
                self.assertEqual(raw_sku, normalize_sku(raw_sku))

    def test_normalizes_full_width_numeric_sku(self):
        self.assertEqual("50113-0112", normalize_sku("５０１１３－０１１２"))

    def test_keeps_existing_alphanumeric_sku_behavior(self):
        self.assertEqual("JMH170044-0741", normalize_sku("jmh170044－0741"))

    def test_rejects_unstructured_or_too_short_numeric_values(self):
        for raw_value in ("12345678", "12-34", "289.96"):
            with self.subTest(raw_value=raw_value):
                self.assertIsNone(normalize_sku(raw_value))


if __name__ == "__main__":
    unittest.main()
