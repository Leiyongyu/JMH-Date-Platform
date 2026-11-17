from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request

from backend.config import settings


def require_internal_access(
    request: Request,
    internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    configured_token = settings.python_internal_api_token
    if configured_token:
        if not internal_token or not secrets.compare_digest(
            internal_token, configured_token
        ):
            raise HTTPException(status_code=401, detail="内部接口令牌无效")
        return

    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(
            status_code=403,
            detail="未配置内部接口令牌时，仅允许本机访问",
        )
