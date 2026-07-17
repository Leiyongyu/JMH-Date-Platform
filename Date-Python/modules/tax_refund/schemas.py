from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskAcceptedData(BaseModel):
    id: int
    task_type: Literal['REFUND_PACKAGE_GENERATE']
    task_status: str = 'PENDING'
    status_url: str


class TaskAcceptedResponse(BaseModel):
    success: bool = True
    data: TaskAcceptedData


class RefundPackageTaskRequest(BaseModel):
    model_config = ConfigDict(extra='allow')

    task_type: str
    output_parent_dir: str = Field(min_length=1)
    declaration_month: str = '202512'
    payer_name: str = 'Hong Kong Cammy Yeson Limited'
    overwrite: bool = False
    export_ids: list[int] | None = None
    created_by: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
