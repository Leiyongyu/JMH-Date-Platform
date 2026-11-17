"""Trusted Java gateway scope; used only behind require_internal_access.

Explicit JSON null means all, [] denies all. Public Java endpoints never accept
this argument: the gateway replaces it from authenticated account roles.
"""
import json

from fastapi import HTTPException, Query


def request_scope(allowed_principals: str | None = Query(default=None)) -> list[str] | None:
    if allowed_principals is None:
        raise HTTPException(status_code=403, detail='缺少服务端数据权限，请更新Java服务')
    try:
        value = json.loads(allowed_principals)
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail='无效的数据权限') from None
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise HTTPException(status_code=403, detail='无效的数据权限')
    return list(dict.fromkeys(v.strip() for v in value))


def owner_predicate(expression: str, owners: list[str] | None) -> tuple[str, list[str]]:
    if owners is None:
        return '1=1', []
    if not owners:
        return '1=0', []
    return f'BINARY TRIM({expression}) IN ({",".join(["%s"] * len(owners))})', list(owners)
