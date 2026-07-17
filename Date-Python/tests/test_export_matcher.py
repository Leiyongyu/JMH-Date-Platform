import unittest
from datetime import date
from unittest.mock import patch

from modules.tax_refund.parsers.export_matcher import ExportMatchError, match_and_enrich_export_records


PDF_RECORD = {
    'customs_declaration_no': '531620260000035324',
    'customs_item_no': '001',
    'declaration_date': date(2026, 1, 5),
    'export_date': date(2026, 1, 6),
    'contract_no': 'FBA15L7CCK57',
    'export_product_code': '8302100000',
    'export_product_name': 'PDF识别名称',
    'sku_normalized': None,
    'unit': '个',
    'export_quantity': 20,
    'fob_amount': 391.8,
}

EXCEL_ITEM = {
    'id': 10,
    'contract_agreement_no': 'FBA15L7CCK57',
    'product_sequence_normalized': '1',
    'export_invoice_no': 'INV15L7CCK57',
    'commodity_code': '8302100000',
    'product_name': '车门铰链',
    'sku': 'JMH60028-0286',
    'transaction_quantity': 20,
    'transaction_unit': '个',
    'statutory_quantity': 21,
    'statutory_unit': '千克',
    'unit_price': 19.59,
    'total_price': 391.8,
    'currency_code': 'USD',
    'parse_status': 'PENDING',
    'parse_message': None,
}


class ExportMatcherTests(unittest.TestCase):
    @patch('services.export_matcher.get_next_sequence_start', return_value=1)
    @patch('services.export_matcher.get_existing_export_identities', return_value={})
    @patch('services.export_matcher.get_current_excel_items_map', return_value=({'1': EXCEL_ITEM}, []))
    def test_merges_by_contract_and_normalized_item_number(self, _source, _identities, _sequence):
        rows, stats = match_and_enrich_export_records(
            [PDF_RECORD], declaration_batch='1', export_date='2026-01-08')
        row = rows[0]
        self.assertEqual('车门铰链', row['export_product_name'])
        self.assertEqual('JMH60028-0286', row['sku_normalized'])
        self.assertEqual('INV15L7CCK57', row['export_invoice_no'])
        self.assertEqual('202601', row['declaration_month'])
        self.assertEqual('001', row['declaration_batch'])
        self.assertEqual(date(2026, 1, 8), row['export_date'])
        self.assertEqual('00000001', row['sequence_no'])
        self.assertEqual('20260100100000001', row['relation_no'])
        self.assertEqual('MATCHED', row['customs_match_status'])
        self.assertEqual(1, stats['matched_count'])

    @patch('services.export_matcher.get_current_excel_items_map', return_value=({}, []))
    def test_requires_customs_excel_to_be_uploaded_first(self, _source):
        with self.assertRaisesRegex(ExportMatchError, '请先导入'):
            match_and_enrich_export_records([PDF_RECORD])

    @patch('services.export_matcher.get_existing_export_identities', return_value={})
    @patch('services.export_matcher.get_current_excel_items_map', return_value=({'1': EXCEL_ITEM}, []))
    def test_batch_and_export_date_are_optional(self, _source, _identities):
        rows, stats = match_and_enrich_export_records([PDF_RECORD])
        self.assertIsNone(rows[0]['declaration_batch'])
        self.assertIsNone(rows[0]['sequence_no'])
        self.assertIsNone(rows[0]['relation_no'])
        self.assertEqual(date(2026, 1, 6), rows[0]['export_date'])
        self.assertIsNone(stats['declaration_batch'])
        self.assertEqual('2026-01-06', stats['export_date'])

    @patch('services.export_matcher.get_existing_export_identities', return_value={})
    @patch('services.export_matcher.get_current_excel_items_map', return_value=({'1': EXCEL_ITEM}, []))
    def test_missing_pdf_export_date_can_remain_empty(self, _source, _identities):
        record = dict(PDF_RECORD, export_date=None)
        rows, stats = match_and_enrich_export_records([record])
        self.assertIsNone(rows[0]['export_date'])
        self.assertIsNone(stats['export_date'])

    @patch('services.export_matcher.get_next_sequence_start', return_value=29)
    @patch('services.export_matcher.get_existing_export_identities', return_value={
        '1': {'declaration_month': '202601', 'declaration_batch': '001',
              'sequence_no': '00000001', 'relation_no': '20260100100000001'}
    })
    @patch('services.export_matcher.get_current_excel_items_map', return_value=({'1': EXCEL_ITEM}, []))
    def test_reupload_keeps_existing_sequence_identity(self, _source, _identities, _sequence):
        rows, stats = match_and_enrich_export_records(
            [PDF_RECORD], declaration_batch='001', export_date='2026-01-09')
        self.assertEqual('00000001', rows[0]['sequence_no'])
        self.assertEqual('20260100100000001', rows[0]['relation_no'])
        self.assertEqual(1, stats['reused_identity_count'])


if __name__ == '__main__':
    unittest.main()
