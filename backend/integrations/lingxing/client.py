from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from ipaddress import ip_address
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from backend.config import settings
from backend.integrations.lingxing.sign import sign
from backend.integrations.lingxing.token_store import load_token, save_token


LOG = logging.getLogger(__name__)


class LingXingClient:
    def __init__(
        self,
        endpoint: str | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.endpoint = (endpoint or settings.lingxing_endpoint).rstrip("/")
        self.app_id = app_id if app_id is not None else settings.lingxing_app_id
        self.app_secret = (
            app_secret if app_secret is not None else settings.lingxing_app_secret
        )
        self.timeout = timeout or settings.lingxing_request_timeout_sec
        self.max_retries = max_retries if max_retries is not None else settings.lingxing_max_retries
        self._token_lock = Lock()
        self._cached_token: dict | None = None

    def token_status(self) -> dict[str, Any]:
        token = self._cached_token or load_token()
        if not token:
            return {
                "configured": self.is_configured(),
                "status": "missing",
                "endpoint": self.endpoint,
                "endpoint_security": self.endpoint_security(),
            }
        expires_at = token.get("expires_at")
        now = datetime.now()
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at and now < expires_at:
            remaining = int((expires_at - now).total_seconds())
            status = (
                "expiring_soon"
                if remaining <= settings.lingxing_token_refresh_before_sec
                else "valid"
            )
        else:
            remaining = 0
            status = "expired"
        return {
            "configured": self.is_configured(),
            "status": status,
            "endpoint": self.endpoint,
            "endpoint_security": self.endpoint_security(),
            "expires_at": expires_at.isoformat(timespec="seconds") if expires_at else None,
            "remaining_seconds": remaining,
            "has_refresh_token": bool(token.get("refresh_token")),
        }

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.app_id and self.app_secret)

    def endpoint_security(self) -> dict[str, Any]:
        parsed = urlsplit(self.endpoint)
        if parsed.scheme == "https":
            return {"level": "ok", "message": "HTTPS endpoint"}
        if parsed.scheme != "http":
            return {"level": "invalid", "message": "Endpoint 必须使用 http 或 https"}
        host = parsed.hostname or ""
        if host in {"localhost", "127.0.0.1", "::1"} or _is_private_ip(host):
            return {"level": "internal_http", "message": "HTTP endpoint 限内网/本机使用"}
        return {
            "level": "insecure_public_http",
            "message": "公网 HTTP 会明文传输领星 token 和业务数据，建议改为 HTTPS",
        }

    def get_access_token(self, force_refresh: bool = False) -> str:
        if not self.is_configured():
            raise ValueError("领星配置不完整，请设置 LINGXING_ENDPOINT、LINGXING_APP_ID、LINGXING_APP_SECRET")
        with self._token_lock:
            token = None if force_refresh else self._cached_token or load_token()
            if token and self._is_token_valid(token):
                self._cached_token = token
                return str(token["access_token"])
            updated = self._refresh_or_fetch(token)
            self._cached_token = updated
            return str(updated["access_token"])

    def post_signed_query_auth(self, path: str, body: dict[str, Any] | None = None) -> dict:
        access_token = self.get_access_token()
        body = body or {}
        timestamp = str(int(time.time()))
        query = {
            "timestamp": timestamp,
            "access_token": access_token,
            "app_key": self.app_id,
        }
        sign_params = {**query, **body}
        query["sign"] = sign(sign_params, self._sign_key())
        return self._post_json(path, body, query)

    def fetch_access_token_response(self) -> dict:
        return self._post_form(
            "api/auth-server/oauth/access-token",
            {"appId": self.app_id, "appSecret": self.app_secret},
        )

    def _refresh_or_fetch(self, existing: dict | None) -> dict:
        refresh_token = existing.get("refresh_token") if existing else None
        if refresh_token:
            try:
                refreshed = self._refresh_token(str(refresh_token))
                if refreshed and self._is_token_valid(refreshed, skew_seconds=0):
                    return refreshed
            except Exception as exc:
                LOG.warning("LingXing token refresh failed, fetching new token: %s", exc)
        return self._fetch_by_app_secret()

    def _refresh_token(self, refresh_token: str) -> dict | None:
        response = self._post_form(
            "api/auth-server/oauth/refresh",
            {"appId": self.app_id, "refreshToken": refresh_token},
        )
        if not _is_success(response.get("code")):
            return None
        return self._extract_and_save_token(response.get("data"))

    def _fetch_by_app_secret(self) -> dict:
        response = self.fetch_access_token_response()
        if not _is_success(response.get("code")):
            raise ValueError(f"领星 access_token 获取失败: code={response.get('code')}, msg={response.get('msg')}")
        token = self._extract_and_save_token(response.get("data"))
        if not token.get("access_token"):
            raise ValueError("领星 access_token 响应缺少 token")
        return token

    def _extract_and_save_token(self, data: Any) -> dict:
        if isinstance(data, str):
            token = {
                "access_token": data,
                "refresh_token": None,
                "expires_at": datetime.now(),
            }
        elif isinstance(data, dict):
            expires_in = _int_value(data.get("expires_in") or data.get("expiresIn"))
            token = {
                "access_token": data.get("access_token") or data.get("accessToken") or data.get("token"),
                "refresh_token": data.get("refresh_token") or data.get("refreshToken"),
                "expires_at": datetime.now() + timedelta(seconds=expires_in) if expires_in > 0 else datetime.now(),
            }
        else:
            raise ValueError("领星 token 响应 data 格式不可识别")
        save_token(token["access_token"], token.get("refresh_token"), token.get("expires_at"))
        return token

    def _is_token_valid(self, token: dict, skew_seconds: int | None = None) -> bool:
        access_token = token.get("access_token")
        expires_at = token.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        skew = settings.lingxing_token_refresh_before_sec if skew_seconds is None else skew_seconds
        return bool(access_token and expires_at and datetime.now() + timedelta(seconds=max(skew, 0)) < expires_at)

    def _post_form(self, path: str, query: dict[str, str]) -> dict:
        return self._execute("POST", path, query=query, body=None)

    def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict:
        return self._execute("POST", path, query=query, body=body)

    def _execute(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(2 ** (attempt - 1))
            try:
                request = self._build_request(method, path, query=query, body=body)
                with urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8")
                    return json.loads(payload) if payload else {}
            except HTTPError as exc:
                payload = exc.read().decode("utf-8", errors="replace")
                if 400 <= exc.code < 500:
                    raise ValueError(f"领星 HTTP {exc.code}: {payload}") from exc
                last_error = ValueError(f"领星 HTTP {exc.code}: {payload}")
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_error = exc
        raise RuntimeError(f"领星 API 请求失败: {last_error}") from last_error

    def _build_request(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Request:
        normalized_path = _normalize_relative_path(path)
        url = f"{self.endpoint}/{normalized_path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json;charset=UTF-8"
        return Request(url, data=data, headers=headers, method=method)

    def _sign_key(self) -> str:
        return self.app_secret if settings.lingxing_sign_key == "app_secret" else self.app_id


def _is_success(code: Any) -> bool:
    return str(code).lower() in {"0", "200", "ok", "success"}


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _normalize_relative_path(path: str) -> str:
    stripped = path.strip()
    lowered = stripped.lower()
    if not stripped:
        raise ValueError("领星 API path 不能为空")
    if lowered.startswith(("http://", "https://")) or "://" in stripped:
        raise ValueError("领星 API path 必须是相对路径，不能传入完整 URL")
    parts = [part for part in stripped.replace("\\", "/").split("/") if part]
    if any(part == ".." for part in parts):
        raise ValueError("领星 API path 不能包含目录穿越片段")
    return "/".join(parts)


def _is_private_ip(host: str) -> bool:
    try:
        parsed = ip_address(host)
    except ValueError:
        return False
    return parsed.is_private or parsed.is_loopback
