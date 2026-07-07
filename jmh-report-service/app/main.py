import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # startup
    if settings.scheduler_enabled:
        from app.etl.scheduler import start_scheduler

        start_scheduler()
        logger.info("scheduler enabled (APScheduler)")
    else:
        logger.info("scheduler disabled (SCHEDULER_ENABLED=false)")

    yield

    # shutdown
    if settings.scheduler_enabled:
        from app.etl.scheduler import shutdown_scheduler

        shutdown_scheduler()


app = FastAPI(
    title="JMH Report Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
