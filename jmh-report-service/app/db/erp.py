from urllib.parse import quote_plus

from sqlalchemy import create_engine
from app.core.config import settings


ERP_DATABASE_URL = (
    f"mysql+pymysql://{settings.erp_db_user}:{quote_plus(settings.erp_db_password)}"
    f"@{settings.erp_db_host}:{settings.erp_db_port}/{settings.erp_db_name}"
    f"?charset=utf8mb4"
)

erp_engine = create_engine(
    ERP_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)
