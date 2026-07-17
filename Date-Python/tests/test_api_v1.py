import io
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import create_app
from modules.tax_refund.task_handlers import _as_bool


class ApiV1Test(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(), raise_server_exceptions=False)

    @patch('api.v1_router.submit_task')
    @patch('api.v1_router.create_task', return_value=81)
    def test_create_refund_task_returns_accepted_resource(self, create_mock, submit_mock):
        response = self.client.post('/api/v1/tasks', json={
            'task_type': 'REFUND_PACKAGE_GENERATE',
            'output_parent_dir': 'D:/output',
            'declaration_month': '202512',
            'overwrite': False,
        })

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers['Location'], '/api/v1/tasks/81')
        self.assertEqual(response.json()['data']['task_status'], 'PENDING')
        create_mock.assert_called_once()
        submit_mock.assert_called_once_with(81)

    def test_file_task_rejects_wrong_extension(self):
        response = self.client.post(
            '/api/v1/tasks',
            data={'task_type': 'FOREX_IMPORT'},
            files={'file': ('wrong.pdf', io.BytesIO(b'test'), 'application/pdf')},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'INVALID_FILE_TYPE')

    @patch('api.v1_router.get_task')
    def test_task_resource_serializes_database_types(self, get_mock):
        get_mock.return_value = {
            'id': 9,
            'task_status': 'SUCCESS',
            'created_at': datetime(2026, 7, 15, 10, 30),
            'result_payload': {'amount': Decimal('12.30')},
        }

        response = self.client.get('/api/v1/tasks/9')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['created_at'], '2026-07-15T10:30:00')
        self.assertEqual(response.json()['data']['result_payload']['amount'], '12.30')

    def test_page_size_is_limited_with_standard_error(self):
        response = self.client.get('/api/v1/tasks?page_size=101')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'BAD_REQUEST')

    def test_openapi_contains_stable_task_endpoint(self):
        response = self.client.get('/openapi.json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('/api/v1/tasks', response.json()['paths'])
        content = response.json()['paths']['/api/v1/tasks']['post']['requestBody']['content']
        self.assertIn('application/json', content)
        self.assertIn('multipart/form-data', content)

class TaskValueConversionTest(unittest.TestCase):
    def test_form_false_is_not_treated_as_true(self):
        self.assertFalse(_as_bool('false'))
        self.assertFalse(_as_bool('0'))
        self.assertTrue(_as_bool('true'))
        self.assertTrue(_as_bool(True))


if __name__ == '__main__':
    unittest.main()
