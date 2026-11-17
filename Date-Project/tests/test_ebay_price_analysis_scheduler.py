"""价格分析刷表接入调度框架：任务注册、共用锁、拒收历史参数、补齐运行记录字段。"""
from __future__ import annotations

from datetime import date

import pytest

from backend.api.router import api_router
from backend.services import scheduler_service

CODE = "ebay_price_analysis_refresh"


def test_refresh_task_is_registered_with_listing_lock():
    spec = scheduler_service.TASK_SPECS[CODE]
    assert CODE in scheduler_service.TASK_CODES
    # 与 listing 同步共用锁：刷表整表读的 ods_ebay_store_listing_latest 由同步按账号逐个替换
    listing = scheduler_service.TASK_SPECS[scheduler_service.EBAY_STORE_LISTING_TASK_CODE]
    assert spec.lock_name(None) == listing.lock_name(None) == "ebay:store-listing:replace"


@pytest.mark.parametrize("kwargs", [
    {"stat_month": "2026-10"}, {"start_date": date(2026, 10, 1)}, {"end_date": date(2026, 10, 31)},
])
def test_refresh_task_rejects_period_args(kwargs):
    with pytest.raises(ValueError, match="当前在售刊登快照"):
        scheduler_service._prepare_run(CODE, kwargs.get("stat_month"), kwargs.get("start_date"),
                                       kwargs.get("end_date"), "req", "job", False)


def test_refresh_result_gets_scheduler_row_counts(monkeypatch):
    monkeypatch.setattr(scheduler_service, "refresh_price_analysis",
                        lambda: {"status": "success", "sync_batch_id": "b1", "rows": 18013})
    result = scheduler_service.TASK_SPECS[CODE].execute(None)
    assert result["extract_rows"] == result["ods_rows"] == 18013
    assert result["sync_batch_id"] == "b1"


def test_price_analysis_routes_are_mounted():
    paths = {route.path for route in api_router.routes}
    for suffix in ("stores", "detail", "sku-listings", "export"):
        assert f"/api/v1/ebay-price-analysis/{suffix}" in paths
    # 看板简化后 overview（KPI / 图表）已删
    assert "/api/v1/ebay-price-analysis/overview" not in paths
    # 页面「刷新数据源」登记接口已删；刷表只走上面的 TaskSpec。
    assert "/api/v1/ebay-price-analysis/refresh" not in paths
