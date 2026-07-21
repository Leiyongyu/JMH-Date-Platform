"""JMH Python 数据服务：FastAPI 主应用入口。"""
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.api.v1.router import router as api_v1_router
from core.config import get_settings
from core.errors import AppError
from core.logging import setup_logging
from core.middleware import (
    AccessLogMiddleware,
    RequestIDMiddleware,
    app_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from infrastructure.task_queue import get_task_queue

# ── 配置与日志 ──
settings = get_settings()
setup_logging()

UPLOAD_FOLDER = str(settings.upload_dir)
MAX_UPLOAD_SIZE = settings.max_upload_mb * 1024 * 1024
TEST_UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_ui', 'index.html')

# ── 应用工厂 ──
application = FastAPI(
    title='JMH ERP Python Data Service',
    version='1.0.0',
    description='面向 Java ERP 的 RESTful + 任务型数据处理 API',
    docs_url='/docs',
    redoc_url='/redoc',
    openapi_url='/openapi.json',
)


def _setup_middleware():
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(AccessLogMiddleware)

    # 上传限制中间件
    @application.middleware('http')
    async def limit_upload_size(request: Request, call_next):
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                if int(content_length) > MAX_UPLOAD_SIZE:
                    return JSONResponse(
                        {
                            'success': False,
                            'error': {
                                'code': 'PAYLOAD_TOO_LARGE',
                                'message': f'上传文件不能超过 {settings.max_upload_mb} MB',
                            },
                        },
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse(
                    {
                        'success': False,
                        'error': {
                            'code': 'INVALID_CONTENT_LENGTH',
                            'message': 'Content-Length 格式错误',
                        },
                    },
                    status_code=400,
                )
        return await call_next(request)

    # 异常处理器（从最具体到最通用）
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(Exception, unhandled_error_handler)


def _setup_routes():
    # 现有 API 路由（路径不变）
    application.include_router(api_v1_router)

    # 测试页面（数据导入 + 任务管理 + 三表查询）
    @application.get('/test-ui', include_in_schema=False)
    @application.get('/test-ui/', include_in_schema=False)
    def test_ui():
        return FileResponse(TEST_UI_FILE, media_type='text/html; charset=utf-8')


def _setup_lifespan():
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        os.makedirs(str(settings.upload_dir), exist_ok=True)
        queue = get_task_queue()
        queue.recover()
        yield

    application.router.lifespan_context = lifespan


_setup_middleware()
_setup_routes()
_setup_lifespan()

app = application

# ── 直接运行 ──
if __name__ == '__main__':
    import sys
    import uvicorn

    port = int(os.environ.get('PORT', '5000'))
    reload_requested = os.environ.get('UVICORN_RELOAD', 'false').lower() in (
        '1', 'true', 'yes', 'on')
    running_under_debugger = sys.gettrace() is not None or 'pydevd' in sys.modules
    reload_enabled = reload_requested and not running_under_debugger
    print('=' * 60)
    print('  JMH Python 数据服务（FastAPI）')
    print(f'  DB: {settings.db_host}:{settings.db_port}/{settings.db_name}')
    print(f'  API:     http://127.0.0.1:{port}/api/v1')
    print(f'  Swagger: http://127.0.0.1:{port}/docs')
    print(f'  Workers: {settings.task_max_workers}')
    print(f'  Reload:  {reload_enabled}')
    print('=' * 60)
    # PyCharm 调试器与 Uvicorn reload 都会派生子进程，两者不能同时启用。
    target = 'app:app' if reload_enabled else app
    uvicorn.run(target, host='0.0.0.0', port=port, reload=reload_enabled)
