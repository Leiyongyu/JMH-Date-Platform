from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import date


class PerformanceRefreshRequest(BaseModel):
    stat_month: str = Field(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    platform: str = Field(default="combined", pattern=r"^(combined|amazon|ebay)$")
    require_all_platforms: bool = False


class SchedulerRunRequest(BaseModel):
    stat_month: str | None = Field(default=None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    pull_month: str | None = Field(default=None, pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    start_date: date | None = None
    end_date: date | None = None
