import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from modules.tax_refund.workflow import RefundWorkflow, WorkflowOptions, WorkflowResult


def purchase(row_id, supplier, sku, quantity, tax_amount, refundable):
    return {
        'id': row_id,
        'invoice_no': f'INV-{row_id}',
        'invoice_date': date(2026, 1, row_id),
        'invoice_item_no': 1,
        'supplier_tax_no': supplier,
        'tax_type': 'V|增值税',
        'product_name': '商品',
        'sku_normalized': sku,
        'unit': '个',
        'purchased_quantity': Decimal(str(quantity)),
        'remaining_quantity': Decimal(str(quantity)),
        'tax_amount': Decimal(str(tax_amount)),
        'tax_rate': Decimal('0.13'),
        'refund_rate': Decimal('0.13'),
        'refundable_tax_amount': Decimal(str(refundable)),
    }


def export(row_id, item_no, sku, quantity, sequence):
    return {
        'id': row_id,
        'customs_declaration_no': '531620260000035324',
        'customs_item_no': str(item_no),
        'contract_no': 'CONTRACT-1',
        'export_invoice_no': 'EXPORT-INV',
        'export_product_code': '8708801000',
        'export_product_name': '空气弹簧',
        'sku_normalized': sku,
        'unit': '个',
        'export_quantity': Decimal(str(quantity)),
        'fob_amount': Decimal('100'),
        'sequence_no': str(sequence).zfill(8),
    }


class RefundWorkflowTests(unittest.TestCase):
    @patch('modules.tax_refund.workflow.get_refund_forex_rows', return_value=[])
    @patch('modules.tax_refund.workflow.get_refund_exports')
    @patch('modules.tax_refund.workflow.get_refund_purchases')
    def test_fifo_allocation_ranks_suppliers_by_allocated_refund(
            self, purchase_source, export_source, _forex_source):
        purchase_source.return_value = [
            purchase(1, 'SUPPLIER-A', 'SKU-A', 10, 130, 130),
            purchase(2, 'SUPPLIER-B', 'SKU-B', 30, 300, 300),
        ]
        export_source.return_value = [
            export(101, 1, 'SKU-A', 5, 12),
            export(102, 2, 'SKU-B', 20, 20),
        ]
        result = WorkflowResult()
        plan = RefundWorkflow()._build_plan(
            WorkflowOptions(output_parent_dir='unused', declaration_month='202601'), result)

        self.assertEqual(['SUPPLIER-B', 'SUPPLIER-A'], [item['tax_id'] for item in plan])
        self.assertEqual(['001', '002'], [item['code'] for item in plan])
        self.assertEqual('20260100100000020', plan[0]['exports'][0]['关联号'])
        self.assertEqual('20260100200000012', plan[1]['exports'][0]['关联号'])
        self.assertEqual(200.0, plan[0]['purchases'][0]['计税金额'])
        self.assertEqual(65.0, plan[1]['purchases'][0]['计税金额'])
        self.assertEqual(0, result.unmatched_export_rows)

    @patch('modules.tax_refund.workflow.get_refund_forex_rows', return_value=[])
    @patch('modules.tax_refund.workflow.get_refund_exports')
    @patch('modules.tax_refund.workflow.get_refund_purchases', return_value=[])
    def test_export_without_matching_inventory_is_reported(
            self, _purchase_source, export_source, _forex_source):
        export_source.return_value = [export(101, 1, 'MISSING-SKU', 5, 1)]
        result = WorkflowResult()
        plan = RefundWorkflow()._build_plan(
            WorkflowOptions(output_parent_dir='unused'), result)
        self.assertEqual([], plan)
        self.assertEqual(1, result.unmatched_export_rows)
        self.assertIn('MISSING-SKU', result.warnings[0])


if __name__ == '__main__':
    unittest.main()
