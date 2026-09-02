from contextlib import contextmanager
from datetime import date
import unittest
from unittest.mock import patch

from backend.integrations.lingxing.domains.base import LingXingDomainBase
from backend.repositories import performance_repository
from backend.services import scheduler_service
from backend.services.amazon_profit_sync_service import (
    month_range,
    previous_natural_month,
    previous_natural_months,
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
        self.commit_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1


class PerformanceSchedulerTest(unittest.TestCase):
    def test_amazon_profit_ods_is_replaced_by_month(self):
        connection = CapturingConnection()

        performance_repository.replace_amz_profit_raw_month(
            connection,
            "2026-08",
            [],
        )

        self.assertTrue(
            any(
                "DELETE FROM ods_lingxing_amz_order_profit_raw"
                in sql
                for sql in connection.cursor_instance.statements
            )
        )

    def test_amazon_profit_default_schedule_runs_monthly_for_previous_month(self):
        connection = CapturingConnection()

        performance_repository._ensure_default_scheduler_task(connection)

        statement = next(
            sql
            for sql in connection.cursor_instance.statements
            if "amz_monthly_order_profit_sync" in sql
        )
        self.assertIn("0 0 22 4 * ?", statement)
        self.assertIn("上一个完整自然月", statement)

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

    def test_previous_natural_months_are_oldest_first(self):
        self.assertEqual(
            previous_natural_months(3, date(2026, 9, 2)),
            ["2026-06", "2026-07", "2026-08"],
        )

    def test_amz_scheduler_defaults_to_only_previous_natural_month(self):
        captured_months = []

        @contextmanager
        def fake_connection():
            yield CapturingConnection()

        def fake_run(months, request_id, trigger_type):
            captured_months.extend(months)
            return self._amz_scheduler_result(months[0])

        with (
            patch.object(
                scheduler_service,
                "previous_natural_month",
                return_value="2026-08",
            ),
            patch.object(
                scheduler_service,
                "_run_amazon_profit_months",
                side_effect=fake_run,
            ),
            patch.object(
                scheduler_service.repo,
                "performance_connection",
                fake_connection,
            ),
            patch.object(
                scheduler_service.repo,
                "insert_scheduler_run",
            ),
        ):
            scheduler_service.run_scheduler_task(
                scheduler_service.AMZ_TASK_CODE,
                request_id="test-default-month",
                trigger_type="job",
            )

        self.assertEqual(captured_months, ["2026-08"])

    def test_amz_scheduler_explicit_month_only_runs_that_month(self):
        captured_months = []

        @contextmanager
        def fake_connection():
            yield CapturingConnection()

        def fake_run(months, request_id, trigger_type):
            captured_months.extend(months)
            return self._amz_scheduler_result(months[0])

        with (
            patch.object(
                scheduler_service,
                "_run_amazon_profit_months",
                side_effect=fake_run,
            ),
            patch.object(
                scheduler_service.repo,
                "performance_connection",
                fake_connection,
            ),
            patch.object(
                scheduler_service.repo,
                "insert_scheduler_run",
            ),
        ):
            scheduler_service.run_scheduler_task(
                scheduler_service.AMZ_TASK_CODE,
                stat_month="2026-07",
                request_id="test-explicit-month",
                trigger_type="manual",
            )

        self.assertEqual(captured_months, ["2026-07"])

    def test_multi_month_profit_result_keeps_java_scheduler_contract(self):
        original_sync = scheduler_service.sync_amazon_monthly_profit
        original_lock = scheduler_service.repo.named_lock

        @contextmanager
        def acquired_lock(_name):
            yield True

        def fake_sync(stat_month, request_id, trigger_source):
            return {
                "sync_batch_id": f"batch-{stat_month}",
                "stat_month": stat_month,
                "start_date": f"{stat_month}-01",
                "end_date": f"{stat_month}-28",
                "extract_rows": 10,
                "remote_rows": 10,
                "ods_rows": 10,
                "dwd_rows": 9,
                "inserted_rows": 1,
                "updated_rows": 8,
                "deleted_rows": 0,
                "skipped_rows": 1,
                "invalid_rows": 0,
                "duplicate_rows": 1,
                "refresh": {
                    "status": "completed",
                    "amz_ranking_rows": 2,
                    "combined_ranking_rows": 3,
                },
            }

        scheduler_service.sync_amazon_monthly_profit = fake_sync
        scheduler_service.repo.named_lock = acquired_lock
        try:
            result = scheduler_service._run_amazon_profit_months(
                ["2026-06", "2026-07", "2026-08"],
                request_id="test-request",
                trigger_type="job",
            )
        finally:
            scheduler_service.sync_amazon_monthly_profit = original_sync
            scheduler_service.repo.named_lock = original_lock

        self.assertEqual(result["stat_month"], "2026-08")
        self.assertEqual(result["stat_months"], ["2026-06", "2026-07", "2026-08"])
        self.assertEqual(result["extract_rows"], 30)
        self.assertEqual(result["dwd_rows"], 27)
        self.assertEqual(result["refresh"]["status"], "completed")
        self.assertEqual(result["refresh"]["amz_ranking_rows"], 6)
        self.assertEqual(result["refresh"]["combined_ranking_rows"], 9)

    @staticmethod
    def _amz_scheduler_result(stat_month):
        return {
            "sync_batch_id": f"batch-{stat_month}",
            "stat_month": stat_month,
            "extract_rows": 0,
            "ods_rows": 0,
            "dwd_rows": 0,
            "refresh": {},
        }

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
