"""Unfiltered listing extraction; only publish a fully validated latest snapshot."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from tempfile import TemporaryFile
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.integrations.lingxing.client import LingXingClient
from backend.repositories import amz_listing_raw_repository as repo
from backend.services.weekly_inventory_api import (
    MAX_ATTEMPTS, RETRY_BUSINESS, _retry_delay, _summary, _transport_failure,
)

TASK_CODE = "lingxing_amz_listing_raw_sync"
TASK_NAME = "领星-AMZ刊登原始数据每周同步"
API = "erp/sc/data/mws/listing"
PAGE_SIZE = 1000
SID_BATCH_SIZE = 20
LOG = logging.getLogger(__name__)


class AmzListingRawSyncError(ValueError):
    def __init__(self, message, *, stage="EXTRACT", metrics=None):
        super().__init__(message)
        self.stage = stage
        self.metrics = metrics or {}


def _request(client, body, batch_id):
    context = f"接口={API} batch={batch_id} sid={body['sid']} offset={body['offset']} length={body['length']}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # This API has a one-token bucket. No concurrent page fetches or nested retries.
        time.sleep(1.1)
        retry_after = None
        try:
            response = client.post_signed_query_auth(API, dict(body))
        except Exception as exc:
            retryable, retry_after, detail = _transport_failure(exc, client)
        else:
            detail = _summary(response, client)
            code = str(response.get("code")) if isinstance(response, dict) else None
            rows = response.get("data") if isinstance(response, dict) else None
            if code == "0" and isinstance(rows, list) and all(isinstance(r, dict) for r in rows):
                return response
            retryable = code in RETRY_BUSINESS
        message = f"AMZ刊登原始接口失败；{context} attempt={attempt}/{MAX_ATTEMPTS} {detail}"
        if retryable and attempt < MAX_ATTEMPTS:
            delay = _retry_delay(attempt, retry_after)
            if delay is not None:
                LOG.warning("%s；重试同一页", message)
                time.sleep(delay)
                continue
        raise AmzListingRawSyncError(message) from None


def _integer(value, name, *, minimum=0):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdecimal():
        raise ValueError(f"AMZ刊登{name}缺失或不是整数")
    result = int(value)
    if result < minimum:
        raise ValueError(f"AMZ刊登{name}超出有效范围")
    return result


def sync_amz_listing_raw():
    batch_id = str(uuid4())
    pulled_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    metrics = {"sync_batch_id": batch_id, "extract_rows": 0, "ods_rows": 0}
    stage = "EXTRACT"
    try:
        sids = repo.shop_sids()
        client = LingXingClient(max_retries=0)
        # Stream to an automatically deleted temporary file, not an unbounded Python list.
        with TemporaryFile(mode="w+t", encoding="utf-8") as spool:
            for start in range(0, len(sids), SID_BATCH_SIZE):
                batch = sids[start:start + SID_BATCH_SIZE]
                offset, expected = 0, None
                fingerprints = set()
                while True:
                    body = {"sid": ",".join(batch), "offset": offset, "length": PAGE_SIZE}
                    response = _request(client, body, batch_id)
                    total = _integer(response.get("total"), "total")
                    if expected is None:
                        expected = total
                    elif total != expected:
                        raise ValueError("AMZ刊登分页期间total发生变化，拒绝发布不完整快照")
                    rows = response["data"]
                    if len(rows) != min(PAGE_SIZE, expected - offset):
                        raise ValueError(f"AMZ刊登分页数量不完整；offset={offset} total={expected} rows={len(rows)}")
                    fingerprint = hashlib.sha256(repo.dumps(rows).encode("utf-8")).hexdigest()
                    if rows and fingerprint in fingerprints:
                        raise ValueError("AMZ刊登接口重复返回相同整页，拒绝覆盖")
                    fingerprints.add(fingerprint)
                    response_meta = {k: v for k, v in response.items() if k != "data"}
                    for index, row in enumerate(rows, 1):
                        sid = _integer(row.get("sid"), "sid", minimum=1)
                        if str(sid) not in batch:
                            raise ValueError("AMZ刊登返回了请求店铺范围外的sid")
                        if not isinstance(row.get("seller_sku"), str) or not row["seller_sku"].strip():
                            raise ValueError("AMZ刊登缺少seller_sku，拒绝静默跳行")
                        for field in ("status", "is_delete"):
                            if _integer(row.get(field), field) not in (0, 1):
                                raise ValueError(f"AMZ刊登{field}不是0或1")
                        metrics["extract_rows"] += 1
                        spool.write(repo.dumps({"row": row, "row_no": metrics["extract_rows"],
                            "request_sids": body["sid"], "offset": offset, "row_in_page": index,
                            "total": total, "response_meta": response_meta}) + "\n")
                    LOG.info("AMZ原始刊登 batch=%s sid=%s offset=%s rows=%s total=%s",
                             batch_id, body["sid"], offset, len(rows), expected)
                    offset += len(rows)
                    if offset == expected:
                        break
            if not metrics["extract_rows"]:
                raise ValueError("全部店铺返回空数据，拒绝清空上一批；请核对上游授权和店铺")
            stage = "LOAD"
            spool.seek(0)
            metrics.update(repo.replace_snapshot((json.loads(line) for line in spool),
                expected_rows=metrics["extract_rows"], batch_id=batch_id, pulled_at=pulled_at, shop_count=len(sids)))
        return {**metrics, "shop_count": len(sids), "stat_month": pulled_at.strftime("%Y-%m")}
    except AmzListingRawSyncError as exc:
        exc.metrics = metrics
        raise
    except Exception as exc:
        # Database and transport exceptions can include data/credentials. Return only safe diagnostics.
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        raise AmzListingRawSyncError(f"AMZ原始刊登同步失败；stage={stage} batch={batch_id}；{detail}",
                                    stage=stage, metrics=metrics) from None
