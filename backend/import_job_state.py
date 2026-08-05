from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from backend.job_state import (
    forget_job as forget_customs_import_job,
    jobs as customs_import_jobs,
    jobs_lock as customs_import_jobs_lock,
    load_job as load_import_job,
    persist_job as persist_import_job,
    record_job as record_customs_import_job,
    snapshot_job as snapshot_customs_import_job,
    update_job as update_customs_import_job,
)
from backend.services.import_service import import_customs_declaration_excel


customs_import_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="customs-folder-import",
)


def process_customs_import_job(
    job_id: str,
    excel_files: list[tuple[bytes, str]],
) -> None:
    update_customs_import_job(
        job_id,
        status="running",
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    processed_rows = 0
    inserted_rows = 0
    updated_rows = 0
    replaced_rows = 0
    try:
        for index, (content, file_name) in enumerate(excel_files, start=1):
            update_customs_import_job(job_id, current_file=file_name)
            try:
                result = import_customs_declaration_excel(content, file_name)
                with customs_import_jobs_lock:
                    job = customs_import_jobs[job_id]
                    job["results"].append(
                        {
                            "file_name": file_name,
                            "contract_no": result.get("contract_no"),
                            "processed_rows": result.get("processed_rows", 0),
                        }
                    )
                    job["succeeded_files"] += 1
                    snapshot = dict(job)
                persist_import_job(snapshot)
                processed_rows += int(result.get("processed_rows", 0))
                inserted_rows += int(result.get("inserted_rows", 0))
                updated_rows += int(result.get("updated_rows", 0))
                replaced_rows += int(result.get("replaced_rows", 0))
            except Exception as exc:
                with customs_import_jobs_lock:
                    job = customs_import_jobs[job_id]
                    job["errors"].append(
                        {"file_name": file_name, "error": str(exc)}
                    )
                    job["failed_files"] += 1
                    snapshot = dict(job)
                persist_import_job(snapshot)
            finally:
                update_customs_import_job(job_id, processed_files=index)

        with customs_import_jobs_lock:
            job = customs_import_jobs[job_id]
            final_status = (
                "completed_with_errors" if job["failed_files"] else "completed"
            )
        update_customs_import_job(
            job_id,
            status=final_status,
            current_file=None,
            completed_at=datetime.now().isoformat(timespec="seconds"),
            processed_rows=processed_rows,
            inserted_rows=inserted_rows,
            updated_rows=updated_rows,
            replaced_rows=replaced_rows,
        )
    except Exception as exc:
        update_customs_import_job(
            job_id,
            status="failed",
            current_file=None,
            completed_at=datetime.now().isoformat(timespec="seconds"),
            fatal_error=str(exc),
        )
    finally:
        forget_customs_import_job(job_id)
