from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.router import api_router
from backend.database import init_database
from backend.infrastructure.exception_handlers import register_exception_handlers
from backend.infrastructure.logging import configure_logging
from backend.infrastructure.request_context import RequestIdMiddleware


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="退税Excel数据上传 API", version="3.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(api_router)
    register_exception_handlers(app)
    return app


app = create_app()


@app.on_event("startup")
def startup() -> None:
    init_database()
