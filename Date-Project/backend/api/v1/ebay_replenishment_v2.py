from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import ebay_replenishment_v2_service as service
from backend.services import ebay_forecast_rule_service as rule_service
from backend.services import ebay_level_rule_service as level_service
from backend.services import ebay_replenishment_sales_type_service as sales_type_service


router = APIRouter(
    prefix="/api/v1/finance/ebay-replenishment-v2",
    dependencies=[Depends(require_internal_access)],
)


class LevelRuleItem(BaseModel):
    rule_no: int = Field(ge=1, le=9)
    condition_expr: str = Field(min_length=1, max_length=500)
    result_level: Literal["S", "A", "B", "C"]
    remark: str | None = Field(default=None, max_length=255)
    status: Literal[0, 1]


class LevelRuleDraft(BaseModel):
    configs: list[LevelRuleItem] = Field(min_length=9, max_length=9)


class LevelRuleSave(LevelRuleDraft):
    revision: str = Field(pattern="^[0-9a-f]{64}$")
    operator: str | None = Field(default=None, max_length=64)


def _level_response(request, action):
    try:
        return success_response(action(), request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        level_service.LOG.exception("产品等级规则操作失败")
        raise HTTPException(status_code=500, detail="产品等级规则操作失败，请检查服务日志") from exc


@router.get("/level-rule")
def list_level_rules(request: Request):
    return _level_response(request, level_service.list_rules)


@router.post("/level-rule")
def save_level_rules(request: Request, payload: LevelRuleSave):
    return _level_response(request, lambda: level_service.save_rules(
        [item.model_dump() for item in payload.configs], payload.revision, payload.operator))


@router.post("/level-rule/validate")
def validate_level_rules(request: Request, payload: LevelRuleDraft):
    return _level_response(request, lambda: level_service.check_rules(
        [item.model_dump() for item in payload.configs])[1])


class ForecastRuleItem(BaseModel):
    rule_no: int = Field(ge=1, le=13)
    product_nature: Literal["新品", "老品"]
    condition_expr: str = Field(max_length=500)
    formula_expr: str = Field(max_length=500)
    remark: str | None = Field(default=None, max_length=255)
    status: Literal[0, 1]


class ForecastRuleDraft(BaseModel):
    configs: list[ForecastRuleItem] = Field(min_length=13, max_length=13)


class ForecastRuleSave(ForecastRuleDraft):
    revision: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]{64}$")
    operator: str | None = Field(default=None, max_length=64)


class ForecastRulePreview(ForecastRuleDraft):
    product_nature: Literal["新品", "老品"] | None = None
    sales_7d: Decimal = Field(ge=0, le=Decimal("1e24"))
    sales_15d: Decimal = Field(ge=0, le=Decimal("1e24"))
    sales_30d: Decimal = Field(ge=0, le=Decimal("1e24"))
    age_days: Decimal | None = Field(default=None, ge=0, le=Decimal("1e24"))


def _rule_response(request: Request, action):
    try:
        return success_response(action(), request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"预估销量2规则操作失败：{exc}") from exc


@router.get("/forecast-rule")
def list_forecast_rules(request: Request):
    return _rule_response(request, rule_service.list_forecast_rules)


@router.post("/forecast-rule")
def save_forecast_rules(request: Request, payload: ForecastRuleSave):
    return _rule_response(request, lambda: rule_service.save_forecast_rules(
        [item.model_dump() for item in payload.configs], payload.revision, payload.operator))


@router.post("/forecast-rule/validate")
def validate_forecast_rules(request: Request, payload: ForecastRuleDraft):
    return _rule_response(request, lambda: rule_service.validate_forecast_rules(
        [item.model_dump() for item in payload.configs]))


@router.post("/forecast-rule/preview")
def preview_forecast_rule(request: Request, payload: ForecastRulePreview):
    return _rule_response(request, lambda: rule_service.preview_forecast(
        [item.model_dump() for item in payload.configs],
        product_nature=payload.product_nature, sales_7d=payload.sales_7d,
        sales_15d=payload.sales_15d, sales_30d=payload.sales_30d, age_days=payload.age_days))


@router.get("/forecast-rule/sku")
def forecast_rule_sku(request: Request, site: str, sku: str):
    return _rule_response(request, lambda: rule_service.forecast_sku_inputs(site, sku))


class FormulaConfigItem(BaseModel):
    product_level: str = Field(min_length=1, max_length=20)
    safety_coefficient: Decimal = Field(ge=0)
    suggest_coefficient: Decimal = Field(ge=0)
    remark: str | None = Field(default=None, max_length=500)


class FormulaConfigSaveRequest(BaseModel):
    configs: list[FormulaConfigItem]
    operator: str | None = Field(default=None, max_length=64)


class SalesTypeSaveRequest(BaseModel):
    site: str = Field(min_length=1, max_length=100)
    sku: str = Field(min_length=1, max_length=255)
    sales_type: Literal["NORMAL", "BRUSH"]
    operator: str | None = Field(default=None, max_length=64)


@router.post("/sales-type")
def save_sales_type(request: Request, payload: SalesTypeSaveRequest):
    try:
        return success_response(
            sales_type_service.save_sales_type(**payload.model_dump()),
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        level_service.LOG.exception("补货2.0销售类型保存失败")
        raise HTTPException(status_code=500, detail="销售类型保存失败，请检查服务日志") from exc


@router.get("/list")
def list_replenishment(
    request: Request,
    site: str | None = None,
    sku: str | None = None,
    product_name: str | None = None,
    product_level: str | None = None,
    product_nature: str | None = None,
    sales_type: Literal["NORMAL", "BRUSH"] | None = None,
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
            sales_type=sales_type,
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


@router.get("/export-data")
def export_replenishment_data(
    request: Request,
    site: str | None = None,
    sku: str | None = None,
    product_level: str | None = None,
    product_nature: str | None = None,
    sales_type: Literal["NORMAL", "BRUSH"] | None = None,
    sort_field: str | None = None,
    sort_order: str | None = None,
):
    """仅供内部Java导出：同一查询计算全部行，不接受分页参数。"""
    try:
        data = service.list_replenishment(
            site=site, sku=sku, product_level=product_level,
            product_nature=product_nature, sales_type=sales_type,
            sort_field=sort_field, sort_order=sort_order, paginate=False,
        )
        return success_response(data, request_id=request.state.request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        level_service.LOG.exception("eBay补货2.0导出查询失败")
        raise HTTPException(status_code=500, detail="eBay补货2.0导出查询失败，请检查服务日志") from exc


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
