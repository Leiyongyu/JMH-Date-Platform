from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None
    request_id: str = ""


def success_response(
    data: Any = None,
    request_id: str = "",
    message: str = "success",
) -> dict[str, Any]:
    return ApiResponse(
        code=0,
        message=message,
        data=data,
        request_id=request_id,
    ).model_dump()


def error_response(
    code: int,
    message: str,
    data: Any = None,
    request_id: str = "",
) -> dict[str, Any]:
    return ApiResponse(
        code=code,
        message=message,
        data=data,
        request_id=request_id,
    ).model_dump()
