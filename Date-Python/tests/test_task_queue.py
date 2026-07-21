import json
import unittest
from unittest.mock import MagicMock, patch

from infrastructure.task_queue import _load_task


class TaskQueueLoadTests(unittest.TestCase):
    @patch('infrastructure.task_queue.get_conn')
    def test_load_task_decodes_mysql_json_strings(self, get_conn):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            'id': 2,
            'request_payload': json.dumps({'declaration_month': '202601'}),
            'result_payload': json.dumps({'success_count': 20}),
        }
        get_conn.return_value.cursor.return_value = cursor

        task = _load_task(2)

        self.assertEqual({'declaration_month': '202601'}, task['request_payload'])
        self.assertEqual({'success_count': 20}, task['result_payload'])
        cursor.close.assert_called_once()
        get_conn.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
