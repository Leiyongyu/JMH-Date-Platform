import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from modules.tax_refund.schemas import ExcelExportRequest


class ExcelExportRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_openapi_contains_all_excel_export_routes(self):
        paths = app.openapi()['paths']
        for path in (
            '/api/v1/export-details/export',
            '/api/v1/purchase-inventory/export',
            '/api/v1/forex-receivables/export',
        ):
            self.assertIn(path, paths)
            self.assertIn('post', paths[path])

    def test_export_request_normalizes_positive_unique_ids(self):
        request = ExcelExportRequest(ids=[3, 1, 3, -5, 0])
        self.assertEqual([3, 1], request.normalized_ids)
        self.assertIsNone(ExcelExportRequest(ids=None).normalized_ids)

    @patch('core.api.v1.router.get_exports_for_excel', return_value=[])
    def test_export_all_returns_excel_stream(self, repository_mock):
        response = self.client.post('/api/v1/export-details/export', json={'ids': None})
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            response.headers['content-type'],
        )
        self.assertTrue(response.content.startswith(b'PK'))
        self.assertIn("filename*=UTF-8''", response.headers['content-disposition'])
        repository_mock.assert_called_once_with(None)

    def test_empty_selection_is_rejected(self):
        response = self.client.post('/api/v1/purchase-inventory/export', json={'ids': []})
        self.assertEqual(422, response.status_code)
        self.assertEqual('EMPTY_EXPORT_SELECTION', response.json()['error']['code'])


if __name__ == '__main__':
    unittest.main()
