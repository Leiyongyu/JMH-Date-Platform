from __future__ import annotations

from pydantic import BaseModel


class CustomsExportRequest(BaseModel):
    customs_declaration_no: str
    declaration_month: str
    declaration_batch: str


class CustomsBatchExportRequest(BaseModel):
    customs_declaration_numbers: list[str]
    declaration_month: str
    declaration_batch: str


class FinalPackageRequest(BaseModel):
    errors: list[dict] = []
