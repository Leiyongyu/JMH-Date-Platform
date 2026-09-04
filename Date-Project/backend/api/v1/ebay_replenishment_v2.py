from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import ebay_replenishment_v2_service as service


router = APIRouter(
    prefix="/api/v1/finance/ebay-replenishment-v2",
    dependencies=[Depends(require_internal_access)],
)


class FormulaConfigItem(BaseModel):
    product_level: str = Field(min_length=1, max_length=20)
    safety_coefficient: Decimal = Field(ge=0)
    suggest_coefficient: Decimal = Field(ge=0)
    remark: str | None = Field(default=None, max_length=500)


class FormulaConfigSaveRequest(BaseModel):
    configs: list[FormulaConfigItem]
    operator: str | None = Field(default=None, max_length=64)


class ForecastFormulaConfigItem(BaseModel):
    rule_group: str = Field(min_length=1, max_length=16)
    tier: int = Field(ge=1, le=5)
    threshold_ratio: Decimal | None = Field(default=None, ge=0)
    weight_7d: Decimal | None = Field(default=None, ge=0)
    weight_15d: Decimal | None = Field(default=None, ge=0)
    weight_30d: Decimal | None = Field(default=None, ge=0)
    month_days: Decimal | None = Field(default=None, gt=0)
    new_age_cap: Decimal | None = Field(default=None, gt=0)
    old_fallback_ratio: Decimal | None = Field(default=None, ge=0)
    remark: str | None = Field(default=None, max_length=255)


class ForecastFormulaConfigSaveRequest(BaseModel):
    configs: list[ForecastFormulaConfigItem]
    operator: str | None = Field(default=None, max_length=64)


@router.get("/list")
def list_replenishment(
    request: Request,
    site: str | None = None,
    sku: str | None = None,
    product_name: str | None = None,
    product_level: str | None = None,
    product_nature: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_field: str | None = None,
    sort_order: str | None = None,
):
    try:
        data = service.list_replenishment(
            site=site,
            sku=sku,
            product_name=product_name,
            product_level=product_level,
            product_nature=product_nature,
            page=page,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
        )
        return success_response(data, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"eBay补货2.0列表查询失败: {exc}"
        ) from exc


@router.get("/formula")
def list_formula_configs(request: Request):
    try:
        return success_response(
            service.list_formula_configs(), request_id=request.state.request_id
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"eBay补货2.0公式配置查询失败: {exc}"
        ) from exc


@router.post("/formula")
def save_formula_configs(request: Request, payload: FormulaConfigSaveRequest):
    try:
        rows = [item.dict() for item in payload.configs]
        data = service.save_formula_configs(rows, payload.operator)
        return success_response(data, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"eBay补货2.0公式配置保存失败: {exc}"
        ) from exc


@router.get("/forecast-formula")
def list_forecast_formula_configs(request: Request):
    try:
        return success_response(
            service.list_forecast_formula_configs(),
            request_id=request.state.request_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"eBay补货2.0预估销量公式查询失败: {exc}"
        ) from exc


@router.post("/forecast-formula")
def save_forecast_formula_configs(
    request: Request, payload: ForecastFormulaConfigSaveRequest
):
    try:
        rows = [item.dict() for item in payload.configs]
        data = service.save_forecast_formula_configs(rows, payload.operator)
        return success_response(data, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"eBay补货2.0预估销量公式保存失败: {exc}"
        ) from exc
