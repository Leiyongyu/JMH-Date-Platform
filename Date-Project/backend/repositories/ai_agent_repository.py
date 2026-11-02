from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.database import agent_db_connection as db_connection

MEMORY_LIMIT = 50


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False,
                      default=lambda v: float(v) if isinstance(v, Decimal) else str(v))


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


# ---------------------------------------------------------------- 运行记录

def create_run(run_id: str, conversation_uuid: str, user_id: int, username: str,
               question: str, request_id: str) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO ai_agent_run
                   (run_id, conversation_uuid, erp_user_id, erp_username, question, status, request_id)
                   VALUES (%s, %s, %s, %s, %s, 'running', %s)""",
                (run_id, conversation_uuid, user_id, username, question, request_id),
            )
        connection.commit()


def update_run(run_id: str, **fields: Any) -> None:
    allowed = {"status", "plan_json", "results_json", "thinking_json", "answer", "error_message", "rounds",
               "tool_calls", "prompt_tokens", "completion_tokens", "model", "completed_at"}
    assignments, values = [], []
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"unknown run field {key}")
        assignments.append(f"{key}=%s")
        values.append(_dumps(value) if key.endswith("_json") else value)
    if not assignments:
        return
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"UPDATE ai_agent_run SET {', '.join(assignments)} WHERE run_id=%s",
                           (*values, run_id))
        connection.commit()


def get_run(user_id: int, run_id: str) -> dict[str, Any] | None:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT run_id, conversation_uuid, question, status, plan_json, results_json, thinking_json, answer,
                      error_message, rounds, tool_calls, prompt_tokens, completion_tokens, model,
                      started_at, updated_at, completed_at
               FROM ai_agent_run WHERE run_id=%s AND erp_user_id=%s""",
            (run_id, user_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute(
            """SELECT seq, round_no, tool_name, status, row_count, duration_ms, error_message
               FROM ai_agent_step WHERE run_id=%s ORDER BY seq""",
            (run_id,),
        )
        steps = list(cursor.fetchall())
    return {
        "runId": row["run_id"], "conversationId": row["conversation_uuid"], "question": row["question"],
        "status": row["status"], "plan": _loads(row["plan_json"]) or [], "results": _loads(row["results_json"]) or [],
        "thinking": _loads(row["thinking_json"]) or [],
        "answer": row["answer"], "error": row["error_message"], "rounds": row["rounds"],
        "toolCalls": row["tool_calls"], "model": row["model"],
        "usage": {"promptTokens": row["prompt_tokens"], "completionTokens": row["completion_tokens"]},
        "startedAt": _iso(row["started_at"]), "updatedAt": _iso(row["updated_at"]),
        "completedAt": _iso(row["completed_at"]),
        "steps": [
            {"seq": s["seq"], "round": s["round_no"], "tool": s["tool_name"], "status": s["status"],
             "rowCount": s["row_count"], "durationMs": s["duration_ms"], "error": s["error_message"]}
            for s in steps
        ],
    }


def insert_step(run_id: str, seq: int, round_no: int, tool_name: str, arguments: Any,
                status: str, row_count: int, duration_ms: int, error: str | None) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO ai_agent_step
                   (run_id, seq, round_no, tool_name, arguments_json, status, row_count, duration_ms, error_message)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, seq, round_no, tool_name, _dumps(arguments), status, row_count,
                 duration_ms, (error or None) and error[:1000]),
            )
        connection.commit()


def mark_stale_runs_failed(older_than_seconds: int) -> int:
    """进程重启后仍为 running 的运行不会再推进，启动时标记为失败。"""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            affected = cursor.execute(
                """UPDATE ai_agent_run SET status='failed', error_message='服务重启，任务已中断，请重新提问',
                          completed_at=CURRENT_TIMESTAMP(3)
                   WHERE status='running' AND updated_at < (CURRENT_TIMESTAMP(3) - INTERVAL %s SECOND)""",
                (older_than_seconds,),
            )
        connection.commit()
    return affected


# ---------------------------------------------------------------- 长期记忆

def list_memories(user_id: int, limit: int = MEMORY_LIMIT) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT id, category, content, updated_at FROM ai_user_memory
               WHERE erp_user_id=%s AND deleted=0 ORDER BY updated_at DESC LIMIT %s""",
            (user_id, min(max(limit, 1), MEMORY_LIMIT)),
        )
        return [
            {"id": row["id"], "category": row["category"], "content": row["content"],
             "updatedAt": _iso(row["updated_at"])}
            for row in cursor.fetchall()
        ]


def save_memory(user_id: int, category: str, content: str, run_id: str | None) -> int:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id FROM ai_user_memory WHERE erp_user_id=%s AND deleted=0 AND content=%s LIMIT 1""",
                (user_id, content),
            )
            existing = cursor.fetchone()
            if existing:
                cursor.execute("UPDATE ai_user_memory SET category=%s WHERE id=%s", (category, existing["id"]))
                memory_id = existing["id"]
            else:
                cursor.execute("SELECT COUNT(*) AS n FROM ai_user_memory WHERE erp_user_id=%s AND deleted=0",
                               (user_id,))
                if cursor.fetchone()["n"] >= MEMORY_LIMIT:
                    raise ValueError(f"长期记忆最多保存{MEMORY_LIMIT}条，请先删除不再需要的记忆")
                cursor.execute(
                    """INSERT INTO ai_user_memory (erp_user_id, category, content, source_run_id)
                       VALUES (%s, %s, %s, %s)""",
                    (user_id, category, content, run_id),
                )
                memory_id = cursor.lastrowid
        connection.commit()
    return int(memory_id)


def delete_memory(user_id: int, memory_id: int) -> bool:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            affected = cursor.execute(
                "UPDATE ai_user_memory SET deleted=1 WHERE id=%s AND erp_user_id=%s AND deleted=0",
                (memory_id, user_id),
            )
        connection.commit()
    return bool(affected)
