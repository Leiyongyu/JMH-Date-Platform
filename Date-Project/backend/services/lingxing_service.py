from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

from backend.integrations.lingxing.client import LingXingClient
from backend.integrations.lingxing.domains.registry import create_domain, describe_domains
from backend.job_state import forget_job, get_job, record_job, update_job


lingxing_sync_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="lingxing-sync",
)


def token_status() -> dict:
    return LingXingClient().token_status()


def refresh_token() -> dict:
    client = LingXingClient()
    client.get_access_token(force_refresh=True)
    return client.token_status()


def probe(path: str, body: dict | None = None) -> dict:
    return LingXingClient().post_signed_query_auth(path, body or {})


def domains() -> list[dict]:
    return describe_domains()


def create_lingxing_sync_job(
    data_type: str,
    path: str,
    params: dict | None = None,
    paginated: bool = True,
    domain: str = "base",
) -> dict:
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "kind": "lingxing_sync",
        "status": "queued",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": None,
        "completed_at": None,
        "total_files": 1,
        "processed_files": 0,
        "succeeded_files": 0,
        "failed_files": 0,
        "skipped_files": [],
        "skipped_file_count": 0,
        "current_file": f"{domain}:{data_type}",
        "processed_rows": 0,
        "inserted_rows": 0,
        "updated_rows": 0,
        "replaced_rows": 0,
        "results": [],
        "errors": [],
        "fatal_error": None,
    }
    record_job(job)
    lingxing_sync_executor.submit(
        run_lingxing_sync_job,
        job_id,
        domain,
        data_type,
        path,
        params or {},
        paginated,
    )
    return job


def run_lingxing_sync_job(
    job_id: str,
    domain: str,
    data_type: str,
    path: str,
    params: dict,
    paginated: bool,
) -> None:
    update_job(
        job_id,
        status="running",
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    try:
        domain_client = create_domain(domain)
        if paginated:
            rows = domain_client.paginated_request(path, params)
            result = {
                "domain": domain,
                "data_type": data_type,
                "path": path,
                "rows": len(rows),
                "sample": rows[:3],
            }
            processed_rows = len(rows)
        else:
            response = domain_client.request(path, params)
            result = {
                "domain": domain,
                "data_type": data_type,
                "path": path,
                "response": response,
            }
            processed_rows = 1
        update_job(
            job_id,
            status="completed",
            completed_at=datetime.now().isoformat(timespec="seconds"),
            current_file=None,
            processed_files=1,
            succeeded_files=1,
            processed_rows=processed_rows,
            results=[result],
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            completed_at=datetime.now().isoformat(timespec="seconds"),
            current_file=None,
            processed_files=1,
            failed_files=1,
            fatal_error=str(exc),
            errors=[
                {
                    "domain": domain,
                    "data_type": data_type,
                    "path": path,
                    "error": str(exc),
                }
            ],
        )
    finally:
        forget_job(job_id)


def get_lingxing_sync_job(job_id: str) -> dict | None:
    job = get_job(job_id)
    return copy.deepcopy(job) if job and job.get("kind") == "lingxing_sync" else None
