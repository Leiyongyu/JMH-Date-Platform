"""Bounded retries and sanitized diagnostics for the three read-only weekly APIs."""
from __future__ import annotations

import errno
import json
import logging
import math
import random
import re
import socket
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import URLError

from backend.integrations.lingxing.client import LingXingHttpError

LOG = logging.getLogger(__name__)
PREFIX = "erp/sc/routing/data/local_inventory/"
ENDPOINTS = {"inventoryDetails", "inventoryBinDetails", "batchGetProductInfo"}
MAX_ATTEMPTS = 4  # initial request + at most three retries, per page/batch
MAX_RETRY_WAIT = 60
RETRY_HTTP = {408, 429, 500, 502, 503, 504}
# Existing LingXing integration identifies this specific code as rate limiting.
# Never guess temporary failures from arbitrary message substrings or unknown codes.
RETRY_BUSINESS = {"3001008"}


class WeeklyRequestError(ValueError):
    """Only contains a sanitized summary, safe for API/job/database error records."""


def safe_text(value, client=None, limit=400):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return "-"
    text = str(value)
    # Also hide known credentials even if the upstream message omits their labels.
    attrs = vars(client) if client is not None else {}
    secrets = [attrs.get("app_id"), attrs.get("app_secret")]
    token = attrs.get("_cached_token")
    if isinstance(token, dict):
        secrets.extend(token.get(k) for k in ("access_token", "refresh_token"))
    for secret in sorted((s for s in secrets if isinstance(s, str) and s), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"https?://[^\s<>\"']+", "[URL REDACTED]", text, flags=re.I)
    text = re.sub(r"(?i)\bBearer\s+[^\s,;\"']+", "Bearer [REDACTED]", text)
    text = re.sub(
        r'''(?ix)(["']?(?:access[_-]?token|refresh[_-]?token|token|secret|app[_-]?(?:key|id|secret)|client[_-]?secret|api[_-]?key|authorization|cookie|password|sign(?:ature)?)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s&,;]+)''',
        r"\1[REDACTED]", text,
    )
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return text[:limit] + ("…" if len(text) > limit else "")


def _summary(response, client):
    if not isinstance(response, dict):
        return f"response_type={type(response).__name__} code=- data_type=- message=-"
    return (
        f"code={safe_text(response.get('code'), client)} "
        f"data_type={type(response.get('data')).__name__} "
        f"upstream_request_id={safe_text(response.get('request_id'), client, 100)} "
        f"message={safe_text(response.get('message') or response.get('msg'), client)}"
    )


def _transport_failure(exc, client):
    """Classify structured exceptions, never parse a raw exception string for retry."""
    current, seen = exc, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, LingXingHttpError):
            try:
                response = json.loads(current.payload)
            except (ValueError, TypeError):
                response = None  # do not log raw HTML/body or request URLs
            return (current.status in RETRY_HTTP, current.retry_after,
                    f"http_status={current.status} {_summary(response, client)}")
        if isinstance(current, (TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return True, None, f"transport={type(current).__name__}"
        if isinstance(current, socket.gaierror):
            return current.errno == socket.EAI_AGAIN, None, "transport=DNS lookup failure"
        if isinstance(current, OSError) and current.errno in {
            errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE,
        }:
            return True, None, f"transport={type(current).__name__}"
        if isinstance(current, URLError) and isinstance(current.reason, BaseException):
            current = current.reason
        else:
            current = current.__cause__
    # No raw exception text: it can include signed URLs/tokens/configuration.
    return False, None, f"transport={type(exc).__name__}（非明确临时错误，未输出原始异常文本）"


def _retry_delay(attempt, retry_after):
    delay = 2 ** attempt + random.uniform(0, 0.5)
    if retry_after:
        try:
            seconds = float(retry_after)
        except (ValueError, TypeError):
            try:
                when = parsedate_to_datetime(str(retry_after))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                seconds = (when - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = 0
        if math.isfinite(seconds):
            # Do not hammer earlier than Retry-After or sleep unboundedly.
            if seconds > MAX_RETRY_WAIT:
                return None
            delay = max(delay, seconds)
    return min(delay, MAX_RETRY_WAIT)


def request_response(client, endpoint, body, *, batch="-", page=1):
    if endpoint not in ENDPOINTS:
        raise ValueError("非周报只读接口，禁止使用周报重试器")
    context = (f"接口={PREFIX}{endpoint} batch={safe_text(batch, client, 100)} "
               f"page={page} offset={body.get('offset', '-')} length={body.get('length', '-')} "
               f"product_count={len(body.get('productIds', []))}")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_after = None
        try:
            # Do not mutate the caller's request or advance offset during retries.
            response = client.post_signed_query_auth(PREFIX + endpoint, dict(body))
        except Exception as exc:
            retryable, retry_after, detail = _transport_failure(exc, client)
        else:
            detail = _summary(response, client)
            code = str(response.get("code")) if isinstance(response, dict) else None
            data = response.get("data") if isinstance(response, dict) else None
            if code == "0" and isinstance(data, list) and all(isinstance(row, dict) for row in data):
                LOG.info("周报接口成功 %s attempt=%s rows=%s", context, attempt, len(data))
                return response
            retryable = code in RETRY_BUSINESS
            if code == "0":
                detail += " reason=响应data或行结构异常"
        message = f"领星周报接口失败；{context} attempt={attempt}/{MAX_ATTEMPTS} {detail}"
        if retryable and attempt < MAX_ATTEMPTS:
            delay = _retry_delay(attempt, retry_after)
            if delay is not None:
                LOG.warning("%s；将在%.2f秒后重试同一页/批次", message, delay)
                time.sleep(delay)
                continue
            message += "；Retry-After超过60秒安全等待上限，停止本次任务"
        elif retryable:
            message += "；重试次数耗尽"
        LOG.error("%s", message)
        # Outside except and suppress context: never leak the signed URL/body in
        # the final LOG.exception, API detail, scheduler record or Java alert.
        raise WeeklyRequestError(message) from None
    raise AssertionError("unreachable")
