"""Internal-only API for 财务中心「运营目标与人效」; ERP enforces end-user RBAC."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pydantic import BaseModel, Field

from backend.api.deps import require_internal_access
from backend.schemas.responses import success_response
from backend.services import ops_target_service as service

router = APIRouter(
    prefix="/api/v1/finance/ops-target",
    dependencies=[Depends(require_internal_access)],
)
LOG = logging.getLogger(__name__)


class OpsTargetUpdate(BaseModel):
    values: dict[str, Any] = Field(..., description="要修改的字段 → 新值；传 null 清空")


def run(action):
    try:
        return success_response(action())
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("运营目标与人效请求失败")
        raise HTTPException(500, detail="运营目标与人效处理失败，请确认迁移已执行并检查服务日志") from exc


@router.get("/report")
def report(year: int | None = Query(None, ge=2020, le=2100)):
    return run(lambda: service.get_report(year))


@router.put("/rows/{year}/{dept_code}")
def update_row(
    payload: OpsTargetUpdate,
    year: int = Path(..., ge=2020, le=2100),
    dept_code: str = Path(..., min_length=1, max_length=32),
    operator: str = Header("", alias="X-Erp-User"),
):
    return run(lambda: service.update_row(year, dept_code, payload.values, operator))
