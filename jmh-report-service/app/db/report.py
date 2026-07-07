from urllib.parse import quote_plus

from sqlalchemy import create_engine
from app.core.config import settings


REPORT_DATABASE_URL = (
    f"mysql+pymysql://{settings.report_db_user}:{quote_plus(settings.report_db_password)}"
    f"@{settings.report_db_host}:{settings.report_db_port}/{settings.report_db_name}"
    f"?charset=utf8mb4"
)

report_engine = create_engine(
    REPORT_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)
