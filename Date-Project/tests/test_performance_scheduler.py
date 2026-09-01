from datetime import date
import unittest

from backend.integrations.lingxing.domains.base import LingXingDomainBase
from backend.repositories import performance_repository
from backend.services.amazon_profit_sync_service import (
    month_range,
    previous_natural_month,
)


class FakePagedDomain(LingXingDomainBase):
    def __init__(self, responses):
        self.responses = iter(responses)

    def request(self, path, body=None):
        return next(self.responses)


class CapturingCursor:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params=None):
        self.statements.append(statement)


class CapturingConnection:
    def __init__(self):
        self.cursor_instance = CapturingCursor()

    def cursor(self):
        return self.cursor_instance


class PerformanceSchedulerTest(unittest.TestCase):
    def test_monthly_inventory_sales_volume_default_schedule_matches_quartz(self):
        connection = CapturingConnection()

        performance_repository._ensure_default_scheduler_task(connection)

        statement = next(
            sql
            for sql in connection.cursor_instance.statements
            if "monthly_inventory_report_sales_volume_sync" in sql
        )
        self.assertIn("0 0 12 1 * ?", statement)
        self.assertIn("每月1日12:00", statement)
        self.assertNotIn("每月2日06:00", statement)

    def test_previous_natural_month_crosses_year(self):
        self.assertEqual(
            previous_natural_month(date(2026, 1, 4)), "2025-12"
        )

    def test_month_range_uses_full_natural_month(self):
        self.assertEqual(
            month_range("2026-02"),
            (date(2026, 2, 1), date(2026, 2, 28)),
        )

    def test_paginated_request_rejects_incomplete_result(self):
        domain = FakePagedDomain(
            [
                {"data": {"list": [{"id": 1}], "total": 2}},
                {"data": {"list": [], "total": 2}},
            ]
        )
        with self.assertRaisesRegex(RuntimeError, "分页数据不完整"):
            domain.paginated_request("/test", page_size=1)

    def test_paginated_request_returns_all_pages(self):
        domain = FakePagedDomain(
            [
                {"data": {"list": [{"id": 1}], "total": 2}},
                {"data": {"list": [{"id": 2}], "total": 2}},
            ]
        )
        self.assertEqual(
            domain.paginated_request("/test", page_size=1),
            [{"id": 1}, {"id": 2}],
        )


if __name__ == "__main__":
    unittest.main()
