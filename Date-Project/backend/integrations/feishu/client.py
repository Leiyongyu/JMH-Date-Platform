"""飞书开放平台多维表格只读客户端；app_secret 与令牌永不进日志。

自建应用用 app_id + app_secret 换 tenant_access_token（有效期约2小时），
之后所有接口带 Authorization: Bearer <token>。令牌只放在内存里，进程重启重新换，
不落库——它两小时就过期，存库带来的泄露面大于省下的那一次请求。

飞书的错误在 HTTP 200 的响应体里：{"code":非0,"msg":"...","data":{...}}。
所以每个响应都要查 code，不能只看 HTTP 状态码。
"""
from __future__ import annotations

import json
import logging
import ssl
import time
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import httpx

from backend.config import settings

TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
TABLES_PATH = "/open-apis/bitable/v1/apps/{app_token}/tables"
RECORDS_PATH = "/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
FIELDS_PATH = "/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
LOG = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
# 令牌失效/过期。飞书用业务码表达，HTTP 仍是 200，所以要显式认这几个码。
TOKEN_INVALID_CODES = frozenset({99991661, 99991663, 99991664, 99991668})
# 频控与服务端临时故障，值得重试。
RETRYABLE_CODES = frozenset({99991400, 1254607, 1255001, 1255040})
# 单次翻页上限，防止表被写爆时无限翻。
MAX_PAGES = 2000


class FeishuRequestError(ValueError):
    """对外的失败原因；只带接口、业务码和飞书的 msg，不带任何凭证。"""


def _invalid_constant(_value):
    raise ValueError("non-finite JSON constant")


def _temporary_transport(exc):
    current, seen = exc, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return False
        current = current.__cause__ or current.__context__
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


def parse_bitable_url(url):
    """从多维表格地址里拆出 (app_token, table_id, view_id)，省得手抄。

    形如 https://<租户>.feishu.cn/base/<app_token>?table=<table_id>&view=<view_id>
    知识库里的 /wiki/<node_token> 地址拿到的不是 app_token，需要先调
    wiki 接口换算，本函数直接拒绝，避免拿着 node_token 去请求得到难懂的报错。
    """
    parts = urlsplit(str(url or "").strip())
    segments = [s for s in parts.path.split("/") if s]
    if "wiki" in segments:
        raise FeishuRequestError("这是知识库(wiki)地址，需要先换算成多维表格app_token；请改用/base/开头的地址")
    if "base" not in segments or segments.index("base") + 1 >= len(segments):
        raise FeishuRequestError("不是多维表格地址，期望形如 /base/<app_token>?table=<table_id>&view=<view_id>")
    query = parse_qs(parts.query)
    app_token = segments[segments.index("base") + 1]
    table_id = (query.get("table") or [""])[0]
    view_id = (query.get("view") or [""])[0]
    if not app_token or not table_id:
        raise FeishuRequestError("地址里缺少 app_token 或 table 参数")
    return app_token, table_id, view_id


def field_text(value):
    """把多维表格的字段值压成一行可读文本，只用于人看（探查、日志）。

    多维表格同一个"文本"字段可能返回裸字符串，也可能返回富文本分段数组
    [{"type":"text","text":"..."}]；人员/关联/附件是对象数组。入库时应当原样
    存 JSON，这里只负责展示，不要拿它的结果做统计。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (str, int, float, Decimal)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(x for x in (field_text(v) for v in value) if x)
    if isinstance(value, dict):
        for key in ("text", "name", "en_name", "value", "link", "file_token"):
            if value.get(key):
                return field_text(value[key])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


class FeishuClient:
    def __init__(self, config=settings, *, transport=None):
        endpoint = config.feishu_endpoint.rstrip("/")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise FeishuRequestError("FEISHU_ENDPOINT必须是无凭证、无查询参数的HTTPS地址")
        if not config.feishu_app_id or not config.feishu_app_secret:
            raise FeishuRequestError("请先在Python服务的.env里配置FEISHU_APP_ID和FEISHU_APP_SECRET")
        self.endpoint = endpoint
        self.app_id = config.feishu_app_id
        self.app_secret = config.feishu_app_secret
        self.retries = max(0, min(config.feishu_max_retries, 6))
        self.interval = max(0.0, config.feishu_min_request_interval_sec)
        self.page_size = max(1, min(config.feishu_page_size, 500))
        self.refresh_before = max(0, config.feishu_token_refresh_before_sec)
        self.next_request_at = 0.0
        self._token = ""
        self._token_expires_at = 0.0
        self.http = httpx.Client(timeout=config.feishu_request_timeout_sec,
                                 follow_redirects=False, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        self._token = ""
        self.http.close()

    # ------------------------------------------------------------------ 令牌

    def token(self, *, force=False):
        if not force and self._token and time.monotonic() < self._token_expires_at:
            return self._token
        # 换令牌这一步不能带 Authorization，凭证只出现在请求体里。
        data = self._call("POST", TOKEN_PATH, body={"app_id": self.app_id, "app_secret": self.app_secret},
                          authorized=False, envelope=False)
        token = data.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuRequestError("飞书未返回tenant_access_token；请核对应用凭证与应用是否已启用")
        expire = data.get("expire")
        seconds = int(expire) if isinstance(expire, (int, Decimal)) else 7200
        self._token = token
        self._token_expires_at = time.monotonic() + max(60, seconds - self.refresh_before)
        return token

    # ------------------------------------------------------------ 多维表格

    def list_tables(self, app_token):
        """这个多维表格里有哪些数据表，形如 {"table_id":"tbl...","name":"卖家级别表"}。"""
        path = TABLES_PATH.format(app_token=app_token)
        return self._paged(path, {"page_size": 100})

    def list_fields(self, app_token, table_id):
        """表的字段定义：字段名、类型、是否主键。设计入库表结构时用。"""
        return self._paged(FIELDS_PATH.format(app_token=app_token, table_id=table_id), {"page_size": 100})

    def _paged(self, path, query):
        """GET 类元数据接口的通用翻页；游标没推进就停下，不然会无限翻同一页。"""
        items, page_token = [], ""
        for _ in range(MAX_PAGES):
            params = dict(query)
            if page_token:
                params["page_token"] = page_token
            data = self._call("GET", path, query=params)
            items.extend(data.get("items") or [])
            page_token = data.get("page_token") or ""
            if not data.get("has_more") or not page_token:
                return items
        raise FeishuRequestError(f"翻页超过{MAX_PAGES}页，疑似分页游标未推进；接口={path}")

    def iter_records(self, app_token, table_id, view_id=""):
        """按视图顺序逐条产出记录，形如 {"record_id": "rec...", "fields": {...}}。

        用「查询记录」接口，它是当前版本；旧的 GET 列出记录接口官方已标注即将下线。
        """
        path = RECORDS_PATH.format(app_token=app_token, table_id=table_id)
        # automatic_fields 指创建时间/创建人这类系统字段，卖家级别表用不上，不取。
        body = {"automatic_fields": False}
        if view_id:
            body["view_id"] = view_id
        page_token = ""
        for _ in range(MAX_PAGES):
            query = {"page_size": self.page_size}
            if page_token:
                query["page_token"] = page_token
            data = self._call("POST", path, query=query, body=body)
            for item in data.get("items") or []:
                yield item
            page_token = data.get("page_token") or ""
            if not data.get("has_more") or not page_token:
                return
        raise FeishuRequestError(f"记录翻页超过{MAX_PAGES}页，疑似分页游标未推进；接口={path}")

    def fetch_records(self, app_token, table_id, view_id="", *, limit=None):
        """一次性取回记录列表；limit 只用于探查，正式取数请用 iter_records。"""
        rows = []
        for item in self.iter_records(app_token, table_id, view_id):
            rows.append(item)
            if limit is not None and len(rows) >= limit:
                break
        return rows

    # ------------------------------------------------------------------ 传输

    def _call(self, method, path, *, query=None, body=None, authorized=True, envelope=True):
        """带限速与有限重试的一次调用；令牌失效时自动换一次再重试。"""
        token_retried = False
        attempt = 0
        while True:
            attempt += 1
            wait = self.next_request_at - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.next_request_at = time.monotonic() + self.interval
            delay = min(30, 2 ** attempt)
            temporary = False
            code = None
            try:
                headers = {"Authorization": f"Bearer {self.token()}"} if authorized else {}
                with self.http.stream(method, self.endpoint + path, params=query,
                                      json=body, headers=headers) as response:
                    status = response.status_code
                    if status != 200:
                        reason = f"HTTP {status}"
                        temporary = status in {429, 500, 502, 503, 504}
                        retry_after = response.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = min(30, max(delay, int(retry_after)))
                    else:
                        payload = self._read(response, path)
                        code = payload.get("code")
                        if code == 0 or code is None:
                            return payload.get("data") or {} if envelope else payload
                        reason = f"飞书业务码 {code}：{str(payload.get('msg') or '')[:200]}"
                        # 令牌可能在翻页途中过期；强制换一次再重试，只做一次。
                        if authorized and code in TOKEN_INVALID_CODES and not token_retried:
                            token_retried = True
                            self.token(force=True)
                            attempt -= 1
                            continue
                        temporary = code in RETRYABLE_CODES
            except FeishuRequestError:
                raise
            except (UnicodeError, ValueError, RecursionError):
                reason = "JSON响应结构或编码异常"
            except httpx.TransportError as exc:
                temporary = _temporary_transport(exc)
                reason = type(exc).__name__
            if not temporary or attempt > self.retries:
                raise FeishuRequestError(
                    f"飞书接口失败；接口={path} attempt={attempt}/{self.retries + 1} reason={reason}"
                ) from None
            LOG.warning("飞书有限重试 path=%s attempt=%s/%s code=%s delay=%ss",
                        path, attempt, self.retries + 1, code, delay)
            time.sleep(delay)

    def _read(self, response, path):
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise FeishuRequestError(f"飞书响应超过安全大小；接口={path}")
            chunks.append(chunk)
        # 金额、数量走 Decimal，不经过 float，避免多维表格里的小数被改写。
        payload = json.loads(b"".join(chunks).decode("utf-8-sig"),
                             parse_float=Decimal, parse_constant=_invalid_constant)
        if not isinstance(payload, dict):
            raise FeishuRequestError(f"飞书响应不是对象；接口={path}")
        return payload
