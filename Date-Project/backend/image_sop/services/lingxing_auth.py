from __future__ import annotations

import time
from base64 import b64encode
from hashlib import md5
from typing import Any
from urllib.parse import quote_plus

import httpx
import orjson
from Crypto.Cipher import AES

AUTH_GET_TOKEN_PATH = "/api/auth-server/oauth/access-token"
AUTH_REFRESH_TOKEN_PATH = "/api/auth-server/oauth/refresh"

TOKEN_EXPIRED_CODES = {2001003, 2001007, 2001008}
IP_WHITELIST_CODE = 3001002


class LingxingAuthError(Exception):
    def __init__(self, message: str, *, code: int | None = None, payload: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


class LingxingAuthClient:
    def __init__(self, app_id: str, app_secret: str, api_base: str) -> None:
        if not app_id or not app_secret:
            raise ValueError("领星 AppID/AppSecret 不能为空")
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_base = api_base.rstrip("/")
        self._cipher = AES.new(app_id.encode("utf-8"), AES.MODE_ECB)
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._access_token:
            await self._update_token()

        for attempt in range(2):
            params = self._build_signed_params(body=body, extra_params=extra_params)
            result = await self._send(method, path, params=params, body=body)
            code = result.get("code")
            if code in (0, "0", 1, "1", "200"):
                return result
            if attempt == 0 and self._is_token_error(code):
                await self._update_token(force_refresh=True)
                continue
            raise self._build_error(result)
        raise LingxingAuthError("领星请求失败")

    async def _update_token(self, *, force_refresh: bool = False) -> None:
        if not force_refresh and self._refresh_token:
            try:
                await self._refresh_access_token()
                return
            except LingxingAuthError:
                pass
        await self._fetch_access_token()

    async def _fetch_access_token(self) -> None:
        params = {"appId": self.app_id, "appSecret": self.app_secret}
        payload = await self._send("POST", AUTH_GET_TOKEN_PATH, params=params, body=None)
        self._apply_token_payload(payload)

    async def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise LingxingAuthError("缺少 refresh_token")
        params = {"appId": self.app_id, "refreshToken": self._refresh_token}
        payload = await self._send("POST", AUTH_REFRESH_TOKEN_PATH, params=params, body=None)
        self._apply_token_payload(payload)

    def _apply_token_payload(self, payload: dict[str, Any]) -> None:
        code = payload.get("code")
        if code not in (0, "0", "200"):
            raise self._build_error(payload, prefix="获取领星 Token 失败")
        data = payload.get("data") or {}
        access_token = str(data.get("access_token", "")).strip()
        if not access_token:
            raise LingxingAuthError("领星 Token 响应缺少 access_token", payload=payload)
        self._access_token = access_token
        refresh_token = str(data.get("refresh_token", "")).strip()
        if refresh_token:
            self._refresh_token = refresh_token

    def _build_signed_params(
        self,
        *,
        body: dict[str, Any] | None,
        extra_params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "app_key": self.app_id,
            "access_token": self._access_token,
            "timestamp": int(time.time()),
        }
        if extra_params:
            params.update(extra_params)
        sign_params = dict(params)
        if body:
            sign_params.update(body)
        params["sign"] = self._generate_sign(sign_params)
        return params

    def _serialize_value(self, value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
        return str(value)

    def _generate_sign(self, params: dict[str, Any]) -> str:
        try:
            from oa_lingxing.signing import generate_sign

            return generate_sign(self.app_id, params, url_encode=True)
        except ImportError:
            items: list[str] = []
            for key in sorted(params.keys()):
                value = params[key]
                if value is None or value == "":
                    continue
                items.append(f"{key}={self._serialize_value(value)}")
            canonical = "&".join(items)
            md5_hex = md5(canonical.encode("utf-8")).hexdigest().upper()
            block_size = AES.block_size
            pad_len = block_size - len(md5_hex) % block_size
            padded = md5_hex + chr(pad_len) * pad_len
            encrypted = self._cipher.encrypt(padded.encode("utf-8"))
            return quote_plus(b64encode(encrypted).decode("utf-8"), safe="")

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any],
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        url = f"{self.api_base}{path}"
        headers = {"Content-Type": "application/json"}
        content: bytes | None = None
        if body is not None:
            content = orjson.dumps(body, option=orjson.OPT_SORT_KEYS)
        try:
            async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
                response = await client.request(
                    method.upper(),
                    url,
                    params=params,
                    content=content,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 403:
                detail = ""
                try:
                    payload = exc.response.json()
                    detail = str(payload.get("message") or payload.get("msg") or "").strip()
                except Exception:
                    detail = ""
                if detail and "ip" in detail.lower():
                    raise LingxingAuthError(
                        "领星授权被拒绝：当前出口 IP 未加入白名单。"
                        "请在领星后台【设置 > 业务配置 > 全局 > 开放接口】添加本机公网 IP。"
                    ) from exc
                raise LingxingAuthError(
                    "领星授权被拒绝(403)。请确认 AppKey/AppSecret 正确，"
                    "并将当前出口公网 IP 加入领星开放接口白名单。"
                ) from exc
            raise LingxingAuthError(f"领星网络请求失败：HTTP {status}") from exc
        except httpx.HTTPError as exc:
            raise LingxingAuthError(f"领星网络请求失败：{exc}") from exc

    @staticmethod
    def _is_token_error(code: Any) -> bool:
        try:
            return int(code) in TOKEN_EXPIRED_CODES
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _build_error(payload: dict[str, Any], *, prefix: str = "领星 API 调用失败") -> LingxingAuthError:
        code = payload.get("code")
        message = str(payload.get("message") or payload.get("msg") or "").strip()
        try:
            numeric_code = int(code)
        except (TypeError, ValueError):
            numeric_code = None
        if numeric_code == IP_WHITELIST_CODE:
            detail = (
                f"{prefix}：当前出口 IP 未加入领星白名单。"
                "请在领星后台【设置 > 业务配置 > 全局 > 开放接口】添加本机公网 IP。"
            )
        elif message:
            detail = f"{prefix}：{message} (code={code})"
        else:
            detail = f"{prefix} (code={code})"
        return LingxingAuthError(detail, code=numeric_code, payload=payload)
