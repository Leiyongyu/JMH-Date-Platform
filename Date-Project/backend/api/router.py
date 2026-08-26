from __future__ import annotations

from fastapi import APIRouter

from backend.api import customs, export, health, import_jobs, inventory, upload
from backend.api.v1 import finance as v1_finance
from backend.api.v1 import health as v1_health
from backend.api.v1 import ai_assistant as v1_ai_assistant
from backend.api.v1 import internal_scheduler as v1_internal_scheduler
from backend.api.v1 import inventory as v1_inventory
from backend.api.v1 import lingxing as v1_lingxing
from backend.api.v1 import ebay_sku_analysis as v1_ebay_sku_analysis


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(inventory.router)
api_router.include_router(upload.router)
api_router.include_router(import_jobs.router)
api_router.include_router(customs.router)
api_router.include_router(export.router)
api_router.include_router(v1_health.router)
api_router.include_router(v1_ai_assistant.router)
api_router.include_router(v1_inventory.router)
api_router.include_router(v1_lingxing.router)
api_router.include_router(v1_finance.router)
api_router.include_router(v1_ebay_sku_analysis.router)
api_router.include_router(v1_internal_scheduler.router)
