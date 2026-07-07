from fastapi import APIRouter
from sqlalchemy import text
from app.db.erp import erp_engine
from app.db.report import report_engine


router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health():
    return {
        "status": "ok",
        "service": "jmh-report-service",
    }


@router.get("/db")
def health_db():
    with erp_engine.connect() as erp_conn:
        erp_conn.execute(text("SELECT 1"))

    with report_engine.connect() as report_conn:
        report_conn.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "erp_db": "ok",
        "report_db": "ok",
    }
