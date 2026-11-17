from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from backend.database import db_connection
from backend.infrastructure.request_context import get_request_id


LOG = logging.getLogger(__name__)
DRAFT_TTL_SECONDS = 7 * 24 * 3600


class ImageSopRepository:
    """MySQL persistence adapter compatible with the original SOP database API."""

    def save_draft(self, draft_id: str, sku: str, data: dict[str, Any]) -> None:
        now = datetime.now()
        source_mode = "ebay" if "ebay" in str((data.get("listing_data") or {}).get("data_source", "")).lower() else "amazon"
        store_sid = data.get("store_sid")
        payload = json.dumps(data, ensure_ascii=False)
        owner_user_id = int(data.get("owner_user_id") or 0)
        owner_username = str(data.get("owner_username") or "")[:64]
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO image_sop_draft
                        (id, owner_user_id, owner_username, sku, source_mode, status,
                         store_sid, data_json, request_id, created_at, updated_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        sku = VALUES(sku), source_mode = VALUES(source_mode),
                        status = VALUES(status), store_sid = VALUES(store_sid),
                        data_json = VALUES(data_json), request_id = VALUES(request_id), updated_at = VALUES(updated_at),
                        expires_at = VALUES(expires_at)
                    """,
                    (
                        draft_id,
                        owner_user_id,
                        owner_username,
                        sku,
                        source_mode,
                        str(data.get("premium_status") or "completed"),
                        store_sid,
                        payload,
                        get_request_id(),
                        now,
                        now,
                        now + timedelta(seconds=DRAFT_TTL_SECONDS),
                    ),
                )
            connection.commit()

    def get_draft(
        self,
        draft_id: str,
        owner_user_id: int | None = None,
        max_age: int = DRAFT_TTL_SECONDS,
    ) -> dict[str, Any] | None:
        cutoff = datetime.now() - timedelta(seconds=max_age)
        with db_connection() as connection:
            with connection.cursor() as cursor:
                if owner_user_id is None:
                    cursor.execute(
                        "SELECT data_json, updated_at, expires_at FROM image_sop_draft WHERE id = %s",
                        (draft_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT data_json, updated_at, expires_at FROM image_sop_draft "
                        "WHERE id = %s AND owner_user_id = %s",
                        (draft_id, owner_user_id),
                    )
                row = cursor.fetchone()
        if not row:
            return None
        if row["updated_at"] < cutoff or row["expires_at"] <= datetime.now():
            self.delete_draft(draft_id)
            return None
        value = row["data_json"]
        if isinstance(value, str):
            value = json.loads(value)
        return value if isinstance(value, dict) else None

    def delete_draft(self, draft_id: str) -> bool:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM image_sop_draft WHERE id = %s", (draft_id,))
                deleted = cursor.rowcount > 0
            connection.commit()
        return deleted

    def clean_expired(self, max_age: int = DRAFT_TTL_SECONDS) -> int:
        cutoff = datetime.now() - timedelta(seconds=max_age)
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM image_sop_draft WHERE expires_at < %s OR updated_at < %s",
                    (datetime.now(), cutoff),
                )
                deleted = cursor.rowcount
            connection.commit()
        if deleted:
            LOG.info("Cleaned %s expired Image SOP drafts", deleted)
        return deleted

    def list_all_drafts(self) -> list[dict[str, Any]]:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, owner_user_id, owner_username, sku, "
                    "UNIX_TIMESTAMP(created_at) AS created_at, data_json "
                    "FROM image_sop_draft ORDER BY created_at DESC"
                )
                rows = cursor.fetchall()
        result = []
        for row in rows:
            value = row["data_json"]
            if isinstance(value, str):
                value = json.loads(value)
            result.append({
                "id": row["id"],
                "owner_user_id": row.get("owner_user_id"),
                "owner_username": row.get("owner_username"),
                "sku": row["sku"],
                "created_at": float(row["created_at"]),
                "data": value,
            })
        return result

    def delete_drafts_batch(self, draft_ids: list[str]) -> int:
        if not draft_ids:
            return 0
        placeholders = ",".join(["%s"] * len(draft_ids))
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM image_sop_draft WHERE id IN ({placeholders})", tuple(draft_ids))
                deleted = cursor.rowcount
            connection.commit()
        return deleted

    def get_ai_profile(self, cache_key: str, listing_version: str, max_age: int) -> dict[str, Any] | None:
        cutoff = datetime.now() - timedelta(seconds=max_age)
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT listing_version, data_json, updated_at, expires_at "
                    "FROM image_sop_ai_profile_cache WHERE cache_key = %s",
                    (cache_key,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        if row["listing_version"] != listing_version or row["updated_at"] < cutoff or row["expires_at"] <= datetime.now():
            self.delete_ai_profile(cache_key)
            return None
        value = row["data_json"]
        if isinstance(value, str):
            value = json.loads(value)
        return value if isinstance(value, dict) else None

    def save_ai_profile(self, cache_key: str, listing_version: str, data: dict[str, Any]) -> None:
        from backend.image_sop.config import get_settings

        now = datetime.now()
        expires_at = now + timedelta(hours=max(1, get_settings().ai_profile_cache_ttl_hours))
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO image_sop_ai_profile_cache
                        (cache_key, listing_version, data_json, created_at, updated_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        listing_version = VALUES(listing_version), data_json = VALUES(data_json),
                        updated_at = VALUES(updated_at), expires_at = VALUES(expires_at)
                    """,
                    (cache_key, listing_version, json.dumps(data, ensure_ascii=False), now, now, expires_at),
                )
            connection.commit()

    def delete_ai_profile(self, cache_key: str) -> bool:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM image_sop_ai_profile_cache WHERE cache_key = %s", (cache_key,))
                deleted = cursor.rowcount > 0
            connection.commit()
        return deleted

    def clean_ai_profiles(self, max_age: int) -> int:
        cutoff = datetime.now() - timedelta(seconds=max_age)
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM image_sop_ai_profile_cache WHERE expires_at < %s OR updated_at < %s",
                    (datetime.now(), cutoff),
                )
                deleted = cursor.rowcount
            connection.commit()
        return deleted

    @property
    def draft_count(self) -> int:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS cnt FROM image_sop_draft")
                row = cursor.fetchone()
        return int(row["cnt"])


_repository = ImageSopRepository()


def init_db(_ignored_path: object = None) -> ImageSopRepository:
    return _repository


def get_db() -> ImageSopRepository:
    return _repository
