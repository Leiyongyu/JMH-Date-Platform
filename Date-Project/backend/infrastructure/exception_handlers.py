from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.infrastructure.request_context import get_request_id
from backend.schemas.responses import error_response


LOG = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
            request: Request,
            exc: StarletteHTTPException) -> JSONResponse:
        message = _detail_message(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                code=exc.status_code,
                message=message,
                data=_detail_data(exc.detail),
                request_id=_request_id(request),
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
            request: Request,
            exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                code=422,
                message="请求参数校验失败",
                data={"errors": jsonable_encoder(exc.errors())},
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
            request: Request,
            exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        LOG.exception("Unhandled request error, request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_response(
                code=500,
                message="服务器内部错误",
                data=None,
                request_id=request_id,
            ),
        )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or get_request_id()


def _detail_message(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        value = detail.get("message") or detail.get("detail")
        if value is not None:
            return str(value)
    return str(detail) if detail is not None else "请求失败"


def _detail_data(detail: Any) -> Any:
    if isinstance(detail, dict):
        return detail.get("data")
    return None
