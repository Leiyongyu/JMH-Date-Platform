from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal


class PerformanceRefreshRequest(BaseModel):
    stat_month: str = Field(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    platform: str = Field(default="combined", pattern=r"^(combined|amazon|ebay)$")
    require_all_platforms: bool = False


class InventoryReportRebuildRequest(BaseModel):
    stat_month: str = Field(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")


class InventoryReportOrderProfitSyncRequest(BaseModel):
    stat_month: str | None = Field(
        default=None,
        pattern=r"^20\d{2}-(0[1-9]|1[0-2])$",
    )


class InventoryReportManualInputItem(BaseModel):
    department_code: str = Field(..., min_length=1, max_length=32)
    local_end_in_transit_qty: Decimal = Field(default=0, ge=0)
    local_end_in_transit_total_cost: Decimal = Field(default=0, ge=0)


class InventoryReportManualInputRequest(BaseModel):
    stat_month: str = Field(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    items: list[InventoryReportManualInputItem] = Field(
        ..., min_length=1, max_length=6
    )
    operator: str | None = Field(default=None, max_length=64)


class SchedulerRunRequest(BaseModel):
    stat_month: str | None = Field(default=None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    pull_month: str | None = Field(default=None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    start_date: date | None = None
    end_date: date | None = None
