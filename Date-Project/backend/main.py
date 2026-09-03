import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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
    # eBay 价格查询工具 — APIRouter 包装为子应用后挂载
    ebay_tool_app = FastAPI(title="eBay 价格查询工具")
    ebay_tool_app.include_router(ebay_tool_router)
    app.mount("/ebay-tool-api", ebay_tool_app, name="ebay-tool")
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
