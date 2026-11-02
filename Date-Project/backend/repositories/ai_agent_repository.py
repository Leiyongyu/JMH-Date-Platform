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
               question: str, request_id: str, source: str = "chat") -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO ai_agent_run
                   (run_id, conversation_uuid, erp_user_id, erp_username, question, status, request_id, source)
                   VALUES (%s, %s, %s, %s, %s, 'running', %s, %s)""",
                (run_id, conversation_uuid, user_id, username, question, request_id, source),
            )
        connection.commit()


def update_run(run_id: str, **fields: Any) -> None:
    allowed = {"status", "plan_json", "results_json", "thinking_json", "verification_json", "answer",
               "error_message", "rounds", "tool_calls", "prompt_tokens", "completion_tokens", "model",
               "completed_at"}
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
            """SELECT run_id, conversation_uuid, question, status, plan_json, results_json, thinking_json,
                      verification_json, answer, error_message, rounds, tool_calls, prompt_tokens,
                      completion_tokens, model, source, started_at, updated_at, completed_at
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
        cursor.execute(
            """SELECT id, category, content, status FROM ai_user_memory
               WHERE source_run_id=%s AND erp_user_id=%s AND deleted=0 ORDER BY id""",
            (run_id, user_id),
        )
        memories = list(cursor.fetchall())
        cursor.execute("SELECT rating, comment FROM ai_agent_feedback WHERE run_id=%s AND erp_user_id=%s",
                       (run_id, user_id))
        feedback = cursor.fetchone()
    return {
        "runId": row["run_id"], "conversationId": row["conversation_uuid"], "question": row["question"],
        "status": row["status"], "plan": _loads(row["plan_json"]) or [], "results": _loads(row["results_json"]) or [],
        "thinking": _loads(row["thinking_json"]) or [],
        "verification": _loads(row["verification_json"]),
        "source": row["source"],
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
        "memories": [{"id": m["id"], "category": m["category"], "content": m["content"], "status": m["status"]}
                     for m in memories],
        "feedback": {"rating": feedback["rating"], "comment": feedback["comment"]} if feedback else None,
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

def list_memories(user_id: int, limit: int = MEMORY_LIMIT, include_pending: bool = False) -> list[dict[str, Any]]:
    """默认只返回已生效的记忆（写进提示词用）；记忆管理页面传 include_pending 同时列出待确认的。"""
    statuses = ("active", "pending") if include_pending else ("active",)
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT id, category, content, status, updated_at FROM ai_user_memory
               WHERE erp_user_id=%s AND deleted=0 AND status IN ({", ".join(["%s"] * len(statuses))})
               ORDER BY status='pending' DESC, updated_at DESC LIMIT %s""",
            (user_id, *statuses, min(max(limit, 1), MEMORY_LIMIT)),
        )
        return [
            {"id": row["id"], "category": row["category"], "content": row["content"], "status": row["status"],
             "updatedAt": _iso(row["updated_at"])}
            for row in cursor.fetchall()
        ]


def save_memory(user_id: int, category: str, content: str, run_id: str | None, status: str = "active") -> int:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, status FROM ai_user_memory WHERE erp_user_id=%s AND deleted=0 AND content=%s LIMIT 1""",
                (user_id, content),
            )
            existing = cursor.fetchone()
            if existing:
                # 已生效的记忆不会因为再次推断而退回待确认
                new_status = "active" if "active" in (existing["status"], status) else status
                cursor.execute("UPDATE ai_user_memory SET category=%s, status=%s WHERE id=%s",
                               (category, new_status, existing["id"]))
                memory_id = existing["id"]
            else:
                cursor.execute("SELECT COUNT(*) AS n FROM ai_user_memory WHERE erp_user_id=%s AND deleted=0",
                               (user_id,))
                if cursor.fetchone()["n"] >= MEMORY_LIMIT:
                    raise ValueError(f"长期记忆最多保存{MEMORY_LIMIT}条，请先删除不再需要的记忆")
                cursor.execute(
                    """INSERT INTO ai_user_memory (erp_user_id, category, content, status, source_run_id)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (user_id, category, content, status, run_id),
                )
                memory_id = cursor.lastrowid
        connection.commit()
    return int(memory_id)


def confirm_memory(user_id: int, memory_id: int) -> bool:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            affected = cursor.execute(
                """UPDATE ai_user_memory SET status='active'
                   WHERE id=%s AND erp_user_id=%s AND deleted=0 AND status='pending'""",
                (memory_id, user_id),
            )
        connection.commit()
    return bool(affected)


def delete_memory(user_id: int, memory_id: int) -> bool:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            affected = cursor.execute(
                "UPDATE ai_user_memory SET deleted=1 WHERE id=%s AND erp_user_id=%s AND deleted=0",
                (memory_id, user_id),
            )
        connection.commit()
    return bool(affected)


# ---------------------------------------------------------------- 用户反馈与运行统计

def save_feedback(user_id: int, run_id: str, rating: int, comment: str | None) -> bool:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM ai_agent_run WHERE run_id=%s AND erp_user_id=%s", (run_id, user_id))
            if not cursor.fetchone():
                return False
            cursor.execute(
                """INSERT INTO ai_agent_feedback (run_id, erp_user_id, rating, comment)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE rating=VALUES(rating), comment=VALUES(comment)""",
                (run_id, user_id, rating, (comment or "").strip()[:500] or None),
            )
        connection.commit()
    return True


def run_stats(days: int) -> dict[str, Any]:
    days = min(max(int(days), 1), 180)
    since = "started_at >= (CURRENT_DATE - INTERVAL %s DAY)"
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT COUNT(*) AS runs,
                       SUM(status='completed') AS completed,
                       SUM(status='failed') AS failed,
                       COUNT(DISTINCT erp_user_id) AS users,
                       AVG(CASE WHEN completed_at IS NOT NULL
                                THEN TIMESTAMPDIFF(MICROSECOND, started_at, completed_at) / 1000 END) AS avg_ms,
                       AVG(rounds) AS avg_rounds,
                       SUM(prompt_tokens) AS prompt_tokens,
                       SUM(completion_tokens) AS completion_tokens,
                       SUM(JSON_UNQUOTE(JSON_EXTRACT(verification_json, '$.status'))='warned') AS warned,
                       SUM(JSON_EXTRACT(verification_json, '$.repaired') IS TRUE) AS repaired
                FROM ai_agent_run WHERE {since}""",
            (days,),
        )
        total = cursor.fetchone() or {}
        cursor.execute(
            f"""SELECT DATE(started_at) AS day, COUNT(*) AS runs, SUM(status='failed') AS failed
                FROM ai_agent_run WHERE {since} GROUP BY DATE(started_at) ORDER BY day""",
            (days,),
        )
        daily = list(cursor.fetchall())
        cursor.execute(
            f"""SELECT s.tool_name, COUNT(*) AS calls,
                       SUM(s.status='completed') AS completed, SUM(s.status='failed') AS failed,
                       SUM(s.status='denied') AS denied, SUM(s.status='invalid') AS invalid,
                       AVG(s.duration_ms) AS avg_ms
                FROM ai_agent_step s INNER JOIN ai_agent_run r ON r.run_id=s.run_id
                WHERE r.{since} GROUP BY s.tool_name ORDER BY calls DESC""",
            (days,),
        )
        tools = list(cursor.fetchall())
        cursor.execute(
            f"""SELECT SUM(f.rating > 0) AS up, SUM(f.rating < 0) AS down
                FROM ai_agent_feedback f INNER JOIN ai_agent_run r ON r.run_id=f.run_id WHERE r.{since}""",
            (days,),
        )
        votes = cursor.fetchone() or {}
        cursor.execute(
            f"""SELECT r.run_id, r.erp_username, r.question, LEFT(r.answer, 300) AS answer, f.comment, f.updated_at
                FROM ai_agent_feedback f INNER JOIN ai_agent_run r ON r.run_id=f.run_id
                WHERE f.rating < 0 AND r.{since} ORDER BY f.updated_at DESC LIMIT 20""",
            (days,),
        )
        down = list(cursor.fetchall())

    def num(value: Any, digits: int = 0) -> float | int:
        value = float(value or 0)
        return round(value, digits) if digits else int(round(value))

    return {
        "days": days,
        "runs": num(total.get("runs")), "completed": num(total.get("completed")), "failed": num(total.get("failed")),
        "users": num(total.get("users")), "avgDurationMs": num(total.get("avg_ms")),
        "avgRounds": num(total.get("avg_rounds"), 2),
        "promptTokens": num(total.get("prompt_tokens")), "completionTokens": num(total.get("completion_tokens")),
        "verificationWarned": num(total.get("warned")), "verificationRepaired": num(total.get("repaired")),
        "feedbackUp": num(votes.get("up")), "feedbackDown": num(votes.get("down")),
        "daily": [{"day": str(d["day"]), "runs": num(d["runs"]), "failed": num(d["failed"])} for d in daily],
        "tools": [
            {"tool": t["tool_name"], "calls": num(t["calls"]), "completed": num(t["completed"]),
             "failed": num(t["failed"]), "denied": num(t["denied"]), "invalid": num(t["invalid"]),
             "avgDurationMs": num(t["avg_ms"])}
            for t in tools
        ],
        "downVoted": [
            {"runId": d["run_id"], "username": d["erp_username"], "question": d["question"], "answer": d["answer"],
             "comment": d["comment"], "at": _iso(d["updated_at"])}
            for d in down
        ],
    }


def down_voted_runs(limit: int = 200) -> list[dict[str, Any]]:
    """评测集导出用：被点踩的提问及用户意见。"""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT r.run_id, r.question, r.answer, f.comment, f.updated_at
               FROM ai_agent_feedback f INNER JOIN ai_agent_run r ON r.run_id=f.run_id
               WHERE f.rating < 0 ORDER BY f.updated_at DESC LIMIT %s""",
            (min(max(limit, 1), 1000),),
        )
        return [{"runId": r["run_id"], "question": r["question"], "answer": r["answer"], "comment": r["comment"],
                 "at": _iso(r["updated_at"])} for r in cursor.fetchall()]


# ---------------------------------------------------------------- 定时简报

BRIEF_LIMIT = 20
BRIEF_COLUMNS = """id, erp_user_id, erp_username, title, question, frequency, weekday, month_day, run_hour, enabled,
                   conversation_uuid, last_run_id, last_run_at, next_run_at, created_at"""


def _brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "userId": row["erp_user_id"], "username": row["erp_username"], "title": row["title"],
        "question": row["question"], "frequency": row["frequency"], "weekday": row["weekday"],
        "monthDay": row["month_day"], "runHour": row["run_hour"], "enabled": bool(row["enabled"]),
        "conversationId": row["conversation_uuid"], "lastRunId": row["last_run_id"],
        "lastRunAt": _iso(row["last_run_at"]), "nextRunAt": _iso(row["next_run_at"]),
        "createdAt": _iso(row["created_at"]),
    }


def list_briefs(user_id: int) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT {BRIEF_COLUMNS} FROM ai_scheduled_brief WHERE erp_user_id=%s AND deleted=0 ORDER BY id",
                       (user_id,))
        return [_brief(row) for row in cursor.fetchall()]


def get_brief(user_id: int, brief_id: int) -> dict[str, Any] | None:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT {BRIEF_COLUMNS} FROM ai_scheduled_brief WHERE id=%s AND erp_user_id=%s AND deleted=0",
                       (brief_id, user_id))
        row = cursor.fetchone()
    return _brief(row) if row else None


def save_brief(user_id: int, username: str, brief_id: int | None, fields: dict[str, Any],
               next_run_at: datetime | None) -> int:
    values = (fields["title"], fields["question"], fields["frequency"], fields.get("weekday"),
              fields.get("month_day"), fields["run_hour"], int(bool(fields["enabled"])), next_run_at)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            if brief_id is None:
                cursor.execute("SELECT COUNT(*) AS n FROM ai_scheduled_brief WHERE erp_user_id=%s AND deleted=0",
                               (user_id,))
                if cursor.fetchone()["n"] >= BRIEF_LIMIT:
                    raise ValueError(f"每人最多设置{BRIEF_LIMIT}个定时简报")
                cursor.execute(
                    """INSERT INTO ai_scheduled_brief
                       (erp_user_id, erp_username, title, question, frequency, weekday, month_day, run_hour, enabled,
                        next_run_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (user_id, username, *values),
                )
                brief_id = cursor.lastrowid
            else:
                affected = cursor.execute(
                    """UPDATE ai_scheduled_brief
                       SET title=%s, question=%s, frequency=%s, weekday=%s, month_day=%s, run_hour=%s, enabled=%s,
                           next_run_at=%s, erp_username=%s
                       WHERE id=%s AND erp_user_id=%s AND deleted=0""",
                    (*values, username, brief_id, user_id),
                )
                if not affected:
                    cursor.execute("SELECT 1 FROM ai_scheduled_brief WHERE id=%s AND erp_user_id=%s AND deleted=0",
                                   (brief_id, user_id))
                    if not cursor.fetchone():
                        raise LookupError("定时简报不存在或无权访问")
        connection.commit()
    return int(brief_id)


def delete_brief(user_id: int, brief_id: int) -> bool:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            affected = cursor.execute(
                "UPDATE ai_scheduled_brief SET deleted=1, enabled=0 WHERE id=%s AND erp_user_id=%s AND deleted=0",
                (brief_id, user_id),
            )
        connection.commit()
    return bool(affected)


def due_briefs(now: datetime, limit: int = 50) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT {BRIEF_COLUMNS} FROM ai_scheduled_brief
                WHERE enabled=1 AND deleted=0 AND next_run_at IS NOT NULL AND next_run_at <= %s
                ORDER BY next_run_at LIMIT %s""",
            (now, min(max(limit, 1), 200)),
        )
        return [_brief(row) for row in cursor.fetchall()]


def claim_brief(user_id: int, brief_id: int, now: datetime, next_run_at: datetime | None, force: bool) -> bool:
    """把下次执行时间推到下一周期，成功才执行；定时任务重复触发时只有一次能抢到。手动立即运行不受到期限制。"""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            if force:  # 手动运行不影响下一次定时执行
                affected = cursor.execute(
                    "UPDATE ai_scheduled_brief SET last_run_at=%s WHERE id=%s AND erp_user_id=%s AND deleted=0",
                    (now, brief_id, user_id),
                )
            else:
                affected = cursor.execute(
                    """UPDATE ai_scheduled_brief SET last_run_at=%s, next_run_at=%s
                       WHERE id=%s AND erp_user_id=%s AND deleted=0 AND enabled=1
                         AND next_run_at IS NOT NULL AND next_run_at <= %s""",
                    (now, next_run_at, brief_id, user_id, now),
                )
        connection.commit()
    return bool(affected)


def set_brief_run(brief_id: int, conversation_uuid: str, run_id: str) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE ai_scheduled_brief SET conversation_uuid=%s, last_run_id=%s WHERE id=%s",
                           (conversation_uuid, run_id, brief_id))
        connection.commit()
