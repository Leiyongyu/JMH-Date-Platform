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
from backend.image_sop.repository import get_db as get_image_sop_repository
from backend.image_sop.config import get_settings as get_image_sop_settings


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
    image_sop_repository = get_image_sop_repository()
    image_sop_repository.clean_expired()
    image_sop_repository.clean_ai_profiles(
        max(1, get_image_sop_settings().ai_profile_cache_ttl_hours) * 3600
    )
