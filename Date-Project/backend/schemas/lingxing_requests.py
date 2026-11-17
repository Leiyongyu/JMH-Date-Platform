from __future__ import annotations

from pydantic import BaseModel, Field


class LingXingSyncRequest(BaseModel):
    data_type: str = Field(..., max_length=80)
    path: str = Field(..., max_length=300)
    params: dict = Field(default_factory=dict)
    paginated: bool = True


class LingXingDomainSyncRequest(BaseModel):
    domain: str = Field(..., max_length=40)
    data_type: str = Field(..., max_length=80)
    path: str = Field(..., max_length=300)
    params: dict = Field(default_factory=dict)
    paginated: bool = True


class LingXingProbeRequest(BaseModel):
    path: str = Field(..., max_length=300)
    body: dict = Field(default_factory=dict)
