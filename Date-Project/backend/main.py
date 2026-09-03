import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.deps import require_internal_access
from backend.api.router import api_router
from backend.database import init_database
from backend.infrastructure.exception_handlers import register_exception_handlers
from backend.infrastructure.logging import configure_logging
from backend.infrastructure.request_context import RequestIdMiddleware
from backend.image_sop.app import app as image_sop_app
from backend.ebay_tool.app import router as ebay_tool_router
from backend.image_sop.cleanup import cleanup_keep_recent


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="JMH Date-Project API", version="3.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(api_router)
    app.mount("/image-sop", image_sop_app, name="image-sop")
    # eBay 价格查询工具：页面与 API 统一挂载，并且只接受 Java 代理的内部调用。
    ebay_tool_app = FastAPI(title="eBay 价格查询工具")

    @ebay_tool_app.middleware("http")
    async def require_ebay_tool_internal_access(request: Request, call_next):
        # FastAPI全局dependencies不会覆盖内部mount的StaticFiles，必须在
        # 子应用中间件层校验，才能同时保护静态页面与全部API。
        try:
            require_internal_access(
                request,
                request.headers.get("X-Internal-Token"),
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.detail},
            )
        return await call_next(request)
    # eBay 工具前端统一读取 response.error。FastAPI 已内置更具体的
    # HTTPException / RequestValidationError 处理器，因此不能只注册
    # Exception，否则业务 4xx 仍会返回 {"detail": ...}。
    @ebay_tool_app.exception_handler(HTTPException)
    async def ebay_tool_http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc.detail)},
            headers=exc.headers,
        )

    @ebay_tool_app.exception_handler(RequestValidationError)
    async def ebay_tool_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        messages = [
            str(error.get("msg") or "").strip()
            for error in exc.errors()
            if str(error.get("msg") or "").strip()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "；".join(messages) or "请求参数校验失败"},
        )

    @ebay_tool_app.exception_handler(Exception)
    async def ebay_tool_unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # 不把内部异常和可能包含的敏感信息直接返回浏览器。
        return JSONResponse(
            status_code=500,
            content={"error": "eBay价格查询服务异常，请稍后重试"},
        )

    ebay_tool_app.include_router(ebay_tool_router)
    # 静态目录必须放在业务路由之后，避免吞掉 /api/*。
    ebay_tool_app.mount(
        "/",
        StaticFiles(
            directory=Path(__file__).resolve().parent.parent
            / "frontend"
            / "public"
            / "ebay-tool",
            html=True,
        ),
        name="ebay-tool-static",
    )
    app.mount("/ebay-tool", ebay_tool_app, name="ebay-tool")
    # 兼容旧 API 地址；共用受保护的子应用，不保留匿名旁路。
    app.mount("/ebay-tool-api", ebay_tool_app, name="ebay-tool-legacy")
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    app.mount(
        "/script-tools",
        StaticFiles(directory=frontend_dist, html=True, check_dir=False),
        name="script-tools-workbench",
    )
    register_exception_handlers(app)
    return app


app = create_app()


@app.get("/script-tools", include_in_schema=False)
async def redirect_script_tools() -> RedirectResponse:
    return RedirectResponse(url="/script-tools/", status_code=307)


@app.on_event("startup")
async def startup() -> None:
    init_database()
    await asyncio.to_thread(cleanup_keep_recent)
    app.state.image_sop_cleanup_task = asyncio.create_task(
        _image_sop_cleanup_loop()
    )


async def _image_sop_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(24 * 3600)
        await asyncio.to_thread(cleanup_keep_recent)


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "image_sop_cleanup_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
