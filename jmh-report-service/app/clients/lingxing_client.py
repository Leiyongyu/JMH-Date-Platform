"""领星 Open API 客户端。

完全对齐 Java 侧 LingxingOpenApiClient / LingxingSignUtils / LingxingAuthService 的签名和鉴权逻辑。

签名流程：
  1. 合并 query 参数 + body 参数
  2. 按 key 字母序拼接: key1=value1&key2=value2&...
  3. MD5 → 大写 hex
  4. AES/ECB/PKCS5Padding 加密（密钥 = appId bytes）
  5. Base64 编码

鉴权：access_token 由 appId + appSecret 换取，缓存并自动续期。
"""

import base64
import hashlib
import json
import logging
import threading
import time
from urllib.parse import urlencode

import requests
from Crypto.Cipher import AES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 签名
# ---------------------------------------------------------------------------

def _sign(params: dict, app_id: str) -> str:
    """领星签名：排序拼接 → MD5 → AES/ECB 加密 → Base64。

    Java 侧调用: LingxingSignUtils.sign(params, properties.getAppId())
    即 AES 密钥使用 appId。
    """
    # 1. 排序拼接
    keys = sorted(params.keys())
    raw = "&".join(f"{k}={_to_sign_value(params[k])}" for k in keys)

    # 2. MD5 大写
    md5_hex = hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    # 3. AES/ECB/PKCS5Padding 加密
    key_bytes = app_id.encode("utf-8")
    # PKCS7 兼容 PKCS5Padding
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    padded = _pkcs7_pad(md5_hex.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)

    # 4. Base64
    return base64.b64encode(encrypted).decode("ascii")


def _to_sign_value(value) -> str:
    """参数值转签名字符串，对齐 Java toStringValue()。

    - None → ""
    - list/tuple → compact JSON (无空格)
    - 其他 → str(value).strip()
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def _pkcs7_pad(data: bytes, block_size: int) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

class LingxingClient:
    """领星 Open API 客户端（线程安全）。"""

    def __init__(
        self,
        endpoint: str,
        app_id: str,
        app_secret: str,
        connect_timeout: int = 60,
        read_timeout: int = 120,
        token_refresh_skew_seconds: int = 300,
    ):
        self._endpoint = endpoint.rstrip("/")
        self._app_id = app_id
        self._app_secret = app_secret
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._token_refresh_skew = token_refresh_skew_seconds

        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json;charset=UTF-8"

        # token 缓存
        self._token_lock = threading.Lock()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0  # epoch seconds

    # ----- token -----

    def get_access_token(self) -> str:
        """获取有效 access_token，缓存过期自动刷新。"""
        now = time.time()
        if self._access_token and now + self._token_refresh_skew < self._expires_at:
            return self._access_token

        with self._token_lock:
            if self._access_token and now + self._token_refresh_skew < self._expires_at:
                return self._access_token
            self._fetch_token()
            return self._access_token

    def _fetch_token(self):
        """appId + appSecret 换取 access_token（参数放 query string，对齐 Java postForm）。"""
        query = urlencode({"appId": self._app_id, "appSecret": self._app_secret})
        url = f"{self._endpoint}/api/auth-server/oauth/access-token?{query}"
        resp = self._session.post(
            url,
            timeout=(self._connect_timeout, self._read_timeout),
        )
        resp.raise_for_status()
        result = resp.json()
        self._check_code(result, "get access_token")
        data = result["data"]
        self._access_token = data.get("access_token") or data.get("accessToken") or data.get("token")
        self._refresh_token = data.get("refresh_token") or data.get("refreshToken")
        expires_in = int(data.get("expires_in", data.get("expiresIn", 0)) or 0)
        self._expires_at = time.time() + (expires_in if expires_in > 0 else 7200)

        logger.info("lingxing access_token acquired, expires_in=%ds", expires_in)

    # ----- 核心请求 -----

    def post_signed_query_auth(self, path: str, body: dict | None = None) -> dict:
        """对齐 Java postSignedQueryAuth：query 放鉴权，body 放 JSON 业务参数。"""
        body = body or {}
        access_token = self.get_access_token()
        timestamp_str = str(int(time.time()))

        # query 参数
        query = {
            "timestamp": timestamp_str,
            "access_token": access_token,
            "app_key": self._app_id,
        }

        # 签名参数集 = query + body
        sign_params = dict(query)
        sign_params.update(body)
        sign = _sign(sign_params, self._app_id)
        query["sign"] = sign

        url = f"{self._endpoint}/{path.lstrip('/')}?{urlencode(query)}"

        for attempt in range(4):
            try:
                resp = self._session.post(
                    url,
                    json=body,
                    timeout=(self._connect_timeout, self._read_timeout),
                )
                if resp.status_code < 200 or resp.status_code >= 600:
                    raise requests.RequestException(f"HTTP {resp.status_code}: {resp.text}")
                if resp.status_code >= 500:
                    logger.warning("lingxing 5xx attempt %d/4", attempt + 1)
                    if attempt < 3:
                        time.sleep(2 ** attempt)
                        continue
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                logger.warning("lingxing I/O error attempt %d/4: %s", attempt + 1, e)
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise

    @staticmethod
    def _check_code(result: dict, context: str = ""):
        code = str(result.get("code", ""))
        if code not in ("0", "200"):
            raise RuntimeError(f"lingxing {context} failed: code={code}, msg={result.get('msg','')}")

    # ----- 业务 API -----

    def get_local_inventory_report_page(
        self,
        start_date: str,
        end_date: str,
        offset: int = 1,
        length: int = 100,
        sys_wid: str | None = None,
    ) -> dict:
        """本地仓库存报表明细（分页）。

        接口: /inventory/center/openapi/storageReport/local/detail/page
        """
        body = {
            "offset": offset,
            "length": length,
            "start_date": start_date,
            "end_date": end_date,
        }
        if sys_wid:
            body["sys_wid"] = sys_wid
        return self.post_signed_query_auth(
            "inventory/center/openapi/storageReport/local/detail/page",
            body,
        )
