"""Bounded retries and sanitized diagnostics for the three read-only weekly APIs."""
from __future__ import annotations

import errno
import json
import logging
import math
import random
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead, RemoteDisconnected
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


# Windows often surfaces a bare OSError whose errno is None while winerror holds
# the Winsock code, so the POSIX errno whitelist alone silently misses resets.
RETRY_ERRNO = {errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE}
RETRY_WINERROR = {10053, 10054, 10060}  # WSAECONNABORTED / WSAECONNRESET / WSAETIMEDOUT
# Unambiguous "connection died or body never finished" cases. The three weekly
# endpoints are read-only queries, so replaying the identical request is safe.
RETRY_TRANSPORT = (
    TimeoutError,
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    RemoteDisconnected,
    IncompleteRead,
    ssl.SSLEOFError,
    ssl.SSLZeroReturnError,
)
MAX_CHAIN_DEPTH = 8


def _exception_chain(exc):
    """Walk the cause chain without reading or logging any raw exception text.

    Prefers URLError.reason and an explicit __cause__; only falls back to
    __context__ when the raiser did not suppress it with ``raise ... from None``.
    Bounded depth and an identity guard keep cyclic chains from looping.
    """
    chain, seen, current = [], set(), exc
    while (
        isinstance(current, BaseException)
        and id(current) not in seen
        and len(chain) < MAX_CHAIN_DEPTH
    ):
        seen.add(id(current))
        chain.append(current)
        if isinstance(current, URLError) and isinstance(current.reason, BaseException):
            current = current.reason
        elif current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            break
    return chain


def _exception_diagnostics(chain):
    """Structured diagnostics only: no response body, URL, token or exception text."""
    parts = ["exception_chain=" + "->".join(type(item).__name__ for item in chain)]
    for index, item in enumerate(chain):
        for field in ("errno", "winerror"):
            value = getattr(item, field, None)
            if isinstance(value, int) and not isinstance(value, bool):
                parts.append(f"cause{index}.{field}={value}")
        if isinstance(item, json.JSONDecodeError):
            # Position and size locate the parse failure; item.doc is the raw body.
            parts.append(
                f"json_line={item.lineno} json_column={item.colno} "
                f"json_position={item.pos} response_chars={len(item.doc)}"
            )
            metadata = getattr(item, "lingxing_response_metadata", {})
            if isinstance(metadata, dict):
                for field in ("http_status", "response_bytes", "content_length"):
                    value = metadata.get(field)
                    if isinstance(value, int) and not isinstance(value, bool):
                        parts.append(f"{field}={value}")
                if metadata.get("content_type") in {
                    "application/json", "text/html", "text/plain",
                    "application/octet-stream", "other", "unknown",
                }:
                    parts.append(f"content_type={metadata['content_type']}")
        elif isinstance(item, UnicodeDecodeError):
            parts.append(f"decode_start={item.start} decode_end={item.end}")
        elif isinstance(item, IncompleteRead):
            # item.partial is response bytes, so only its length is reported.
            parts.append(f"partial_bytes={len(item.partial)}")
            if isinstance(item.expected, int):
                parts.append(f"expected_remaining_bytes={item.expected}")
        elif isinstance(item, URLError) and isinstance(item.reason, str):
            # A string reason ends the walk; report its shape, never its content.
            parts.append(f"cause{index}.reason_type=str reason_chars={len(item.reason)}")
    return " ".join(parts)


def _transport_failure(exc, client):
    """Retry known temporary failures and EOF JSON errors on read-only requests.

    The previous version walked the same chain but reported ``type(exc).__name__``,
    which is always the outermost RuntimeError wrapper from LingXingClient, so
    every underlying cause was discarded. The diagnostics string fixes that.
    """
    chain = _exception_chain(exc)
    diagnostics = _exception_diagnostics(chain)

    # Certificate failures must never be retried away or silenced by disabling TLS.
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return False, None, f"reason=TLS证书校验失败 {diagnostics}"

    for current in chain:
        if isinstance(current, LingXingHttpError):
            try:
                response = json.loads(current.payload)
            except (ValueError, TypeError):
                response = None  # do not log raw HTML/body or request URLs
            return (current.status in RETRY_HTTP, current.retry_after,
                    f"http_status={current.status} {_summary(response, client)} {diagnostics}")
        if isinstance(current, json.JSONDecodeError):
            # EOF is consistent with an incomplete response, not proof of its
            # cause. Replay only this read-only page within the existing budget;
            # never accept partial data or retry arbitrary JSON syntax errors.
            at_eof = current.pos == len(current.doc)
            reason = "JSON响应末尾解析失败" if at_eof else "JSON非末尾解析失败"
            return at_eof, None, f"reason={reason} {diagnostics}"
        if isinstance(current, RETRY_TRANSPORT):
            return True, None, f"transport={type(current).__name__} {diagnostics}"
        if isinstance(current, socket.gaierror):
            # Only a temporary resolver failure is worth replaying.
            return (current.errno == socket.EAI_AGAIN, None,
                    f"transport=DNS lookup failure {diagnostics}")
        if isinstance(current, OSError) and (
            current.errno in RETRY_ERRNO
            or getattr(current, "winerror", None) in RETRY_WINERROR
        ):
            return True, None, f"transport={type(current).__name__} {diagnostics}"
    # Unknown RuntimeError and unknown SSL/OSError: nothing
    # proves these are temporary, so stop, but now with the chain recorded.
    return False, None, f"transport={type(exc).__name__} reason=非明确临时错误 {diagnostics}"


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
