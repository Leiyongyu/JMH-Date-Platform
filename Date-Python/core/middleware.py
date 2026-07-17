"""应用中间件：请求ID、异常处理、访问日志"""
import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.errors import AppError

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 X-Request-ID"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """结构化访问日志"""

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response: Response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000

        logger.info(
            "%s %s status=%s elapsed=%.2fms client=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request.client.host if request.client else "-",
        )
        return response


async def app_error_handler(request: Request, exc: AppError):
    """统一序列化 AppError 及其子类"""
    from fastapi.responses import JSONResponse

    body = {
        "success": False,
        "error": {
            "code": exc.error_code,
            "message": exc.message,
        },
    }
    if exc.details:
        body["error"]["details"] = exc.details

    logger.warning("app_error path=%s code=%s message=%s", request.url.path, exc.error_code, exc.message)
    return JSONResponse(body, status_code=exc.http_status)


async def validation_error_handler(request: Request, exc):
    """Pydantic 请求验证错误"""
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    return JSONResponse(
        {
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数不合法",
                "details": errors,
            },
        },
        status_code=422,
    )


async def http_exception_handler(request: Request, exc):
    """Starlette HTTPException"""
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    status_code = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    detail = str(exc.detail) if isinstance(exc, StarletteHTTPException) else "Internal Error"

    return JSONResponse(
        {
            "success": False,
            "error": {
                "code": detail.upper().replace(" ", "_"),
                "message": detail,
            },
        },
        status_code=status_code,
    )


async def unhandled_error_handler(request: Request, exc: Exception):
    """未预期的异常（兜底）"""
    from fastapi.responses import JSONResponse

    logger.exception("unhandled_error path=%s", request.url.path)

    return JSONResponse(
        {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务端处理失败",
            },
        },
        status_code=500,
    )
