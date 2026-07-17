"""数据库连接管理 — mysql-connector-python 原生连接池。

Python 3.14 稳定后可以切换到 SQLAlchemy asyncmy。
"""
from __future__ import annotations

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

from core.config import get_settings

_pool: MySQLConnectionPool | None = None
_jmh_pool: MySQLConnectionPool | None = None


def _build_config(db_name: str, prefix: str = "") -> dict:
    settings = get_settings()
    if prefix:
        return {
            "host": getattr(settings, f"{prefix}db_host"),
            "port": getattr(settings, f"{prefix}db_port"),
            "user": getattr(settings, f"{prefix}db_user"),
            "password": getattr(settings, f"{prefix}db_password"),
            "database": db_name,
            "charset": "utf8mb4",
            "autocommit": False,
        }
    return {
        "host": settings.db_host,
        "port": settings.db_port,
        "user": settings.db_user,
        "password": settings.db_password,
        "database": db_name,
        "charset": "utf8mb4",
        "autocommit": False,
    }


def get_conn():
    """从连接池获取 export_tax_refund 库连接。兼容旧 models/*.py 调用。"""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = MySQLConnectionPool(
            pool_name="export_tax_refund_pool",
            pool_size=settings.db_pool_size,
            pool_reset_session=True,
            **_build_config(settings.db_name),
        )
    return _pool.get_connection()


def get_jmh_conn():
    """从连接池获取 jmh_data_platform 库连接。"""
    global _jmh_pool
    if _jmh_pool is None:
        settings = get_settings()
        _jmh_pool = MySQLConnectionPool(
            pool_name="jmh_data_platform_pool",
            pool_size=3,
            pool_reset_session=True,
            **_build_config(settings.jmh_db_name, prefix="jmh_"),
        )
    return _jmh_pool.get_connection()
