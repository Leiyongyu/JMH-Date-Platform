from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskAcceptedData(BaseModel):
    id: int
    task_type: str
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


class RefundPackageReverseTaskRequest(BaseModel):
    task_type: Literal['REFUND_PACKAGE_REVERSE']
    generation_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


class ExcelExportRequest(BaseModel):
    """ids为空导出全部；有值时只导出所选主键。"""
    ids: list[int] | None = None

    @property
    def normalized_ids(self) -> list[int] | None:
        if self.ids is None:
            return None
        return list(dict.fromkeys(item for item in self.ids if item > 0))


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
