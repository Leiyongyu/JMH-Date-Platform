from __future__ import annotations

import json
from threading import Lock

from backend.database import db_connection


jobs: dict[str, dict] = {}
jobs_lock = Lock()


def persist_job(job: dict) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO import_jobs (
                    job_id, kind, status, created_at, started_at, completed_at,
                    total_files, processed_files, succeeded_files, failed_files,
                    skipped_file_count, current_file, processed_rows, inserted_rows,
                    updated_rows, replaced_rows, skipped_files_json, results_json,
                    errors_json, fatal_error
                ) VALUES (
                    %(job_id)s, %(kind)s, %(status)s, %(created_at)s,
                    %(started_at)s, %(completed_at)s, %(total_files)s,
                    %(processed_files)s, %(succeeded_files)s, %(failed_files)s,
                    %(skipped_file_count)s, %(current_file)s, %(processed_rows)s,
                    %(inserted_rows)s, %(updated_rows)s, %(replaced_rows)s,
                    %(skipped_files_json)s, %(results_json)s, %(errors_json)s,
                    %(fatal_error)s
                )
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    started_at = VALUES(started_at),
                    completed_at = VALUES(completed_at),
                    processed_files = VALUES(processed_files),
                    succeeded_files = VALUES(succeeded_files),
                    failed_files = VALUES(failed_files),
                    skipped_file_count = VALUES(skipped_file_count),
                    current_file = VALUES(current_file),
                    processed_rows = VALUES(processed_rows),
                    inserted_rows = VALUES(inserted_rows),
                    updated_rows = VALUES(updated_rows),
                    replaced_rows = VALUES(replaced_rows),
                    skipped_files_json = VALUES(skipped_files_json),
                    results_json = VALUES(results_json),
                    errors_json = VALUES(errors_json),
                    fatal_error = VALUES(fatal_error)
                """,
                _serialize_job(job),
            )
        connection.commit()


def load_job(job_id: str) -> dict | None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM import_jobs WHERE job_id = %s", (job_id,))
            row = cursor.fetchone()
    if row is None:
        return None
    return {
        "job_id": row["job_id"],
        "kind": row["kind"],
        "status": row["status"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "total_files": row["total_files"],
        "processed_files": row["processed_files"],
        "succeeded_files": row["succeeded_files"],
        "failed_files": row["failed_files"],
        "skipped_files": json.loads(row["skipped_files_json"] or "[]"),
        "skipped_file_count": row["skipped_file_count"],
        "current_file": row["current_file"],
        "processed_rows": row["processed_rows"],
        "inserted_rows": row["inserted_rows"],
        "updated_rows": row["updated_rows"],
        "replaced_rows": row["replaced_rows"],
        "results": json.loads(row["results_json"] or "[]"),
        "errors": json.loads(row["errors_json"] or "[]"),
        "fatal_error": row["fatal_error"],
    }


def snapshot_job(job_id: str) -> dict:
    with jobs_lock:
        return dict(jobs[job_id])


def get_cached_job(job_id: str) -> dict | None:
    with jobs_lock:
        job = jobs.get(job_id)
    return dict(job) if job else None


def get_job(job_id: str) -> dict | None:
    return get_cached_job(job_id) or load_job(job_id)


def record_job(job: dict) -> None:
    with jobs_lock:
        jobs[job["job_id"]] = job
    persist_job(job)


def update_job(job_id: str, **changes) -> None:
    with jobs_lock:
        job = jobs[job_id]
        job.update(changes)
        snapshot = dict(job)
    persist_job(snapshot)


def forget_job(job_id: str) -> None:
    with jobs_lock:
        jobs.pop(job_id, None)


def _serialize_job(job: dict) -> dict:
    return {
        **job,
        "skipped_files_json": json.dumps(
            job.get("skipped_files", []), ensure_ascii=False
        ),
        "results_json": json.dumps(job.get("results", []), ensure_ascii=False),
        "errors_json": json.dumps(job.get("errors", []), ensure_ascii=False),
    }
