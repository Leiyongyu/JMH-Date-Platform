from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from backend.database import db_connection


class ConversationNotFoundError(LookupError):
    pass


class AiConversationRepository:
    def create(self, user_id: int, username: str, title: str = "新对话") -> dict[str, Any]:
        conversation_uuid = str(uuid4())
        with db_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO ai_conversations
                        (conversation_uuid,erp_user_id,erp_username,title)
                        VALUES (%s,%s,%s,%s)
                        """,
                        (conversation_uuid, user_id, username, title),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.get_summary(user_id, conversation_uuid)

    def list_for_user(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 100)
        with db_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conversation_uuid,title,message_count,last_message_preview,
                       created_at,updated_at
                FROM ai_conversations
                WHERE erp_user_id=%s
                ORDER BY updated_at DESC,id DESC
                LIMIT %s
                """,
                (user_id, safe_limit),
            )
            return [self._conversation(row) for row in cursor.fetchall()]

    def get_summary(self, user_id: int, conversation_uuid: str) -> dict[str, Any]:
        with db_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conversation_uuid,title,message_count,last_message_preview,
                       created_at,updated_at
                FROM ai_conversations
                WHERE erp_user_id=%s AND conversation_uuid=%s
                LIMIT 1
                """,
                (user_id, conversation_uuid),
            )
            row = cursor.fetchone()
        if not row:
            raise ConversationNotFoundError(conversation_uuid)
        return self._conversation(row)

    def get_detail(self, user_id: int, conversation_uuid: str) -> dict[str, Any]:
        conversation = self.get_summary(user_id, conversation_uuid)
        with db_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.id,m.role,m.content,m.is_error,m.model,
                       m.prompt_tokens,m.completion_tokens,m.total_tokens,m.created_at
                FROM ai_messages m
                INNER JOIN ai_conversations c ON c.id=m.conversation_id
                WHERE c.erp_user_id=%s AND c.conversation_uuid=%s
                ORDER BY m.id
                """,
                (user_id, conversation_uuid),
            )
            messages = [self._message(row) for row in cursor.fetchall()]
        return {**conversation, "messages": messages}

    def context_messages(
        self, user_id: int, conversation_uuid: str, limit: int = 29
    ) -> list[dict[str, str]]:
        safe_limit = min(max(int(limit), 1), 30)
        with db_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.role,m.content
                FROM ai_messages m
                INNER JOIN ai_conversations c ON c.id=m.conversation_id
                WHERE c.erp_user_id=%s AND c.conversation_uuid=%s
                  AND m.is_error=0
                ORDER BY m.id DESC
                LIMIT %s
                """,
                (user_id, conversation_uuid, safe_limit),
            )
            rows = list(cursor.fetchall())
        rows.reverse()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def append_message(
        self,
        user_id: int,
        username: str,
        conversation_uuid: str,
        role: str,
        content: str,
        *,
        request_id: str | None = None,
        is_error: bool = False,
        model: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        first_message_title: str | None = None,
    ) -> int:
        preview = " ".join(content.split())[:500]
        with db_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id,message_count
                        FROM ai_conversations
                        WHERE erp_user_id=%s AND conversation_uuid=%s
                        FOR UPDATE
                        """,
                        (user_id, conversation_uuid),
                    )
                    conversation = cursor.fetchone()
                    if not conversation:
                        raise ConversationNotFoundError(conversation_uuid)
                    cursor.execute(
                        """
                        INSERT INTO ai_messages
                        (conversation_id,role,content,is_error,request_id,model,
                         prompt_tokens,completion_tokens,total_tokens)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            conversation["id"], role, content, int(is_error), request_id,
                            model, max(0, int(prompt_tokens or 0)),
                            max(0, int(completion_tokens or 0)),
                            max(0, int(total_tokens or 0)),
                        ),
                    )
                    message_id = int(cursor.lastrowid)
                    title = (
                        first_message_title
                        if role == "user" and int(conversation["message_count"]) == 0
                        else None
                    )
                    cursor.execute(
                        """
                        UPDATE ai_conversations
                        SET erp_username=%s,
                            title=COALESCE(%s,title),
                            message_count=message_count+1,
                            last_message_preview=%s,
                            updated_at=CURRENT_TIMESTAMP(3)
                        WHERE id=%s
                        """,
                        (username, title, preview, conversation["id"]),
                    )
                connection.commit()
                return message_id
            except Exception:
                connection.rollback()
                raise

    def refresh_username(self, user_id: int, username: str) -> None:
        with db_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE ai_conversations SET erp_username=%s WHERE erp_user_id=%s",
                        (username, user_id),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def delete(self, user_id: int, conversation_uuid: str) -> bool:
        with db_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM ai_conversations WHERE erp_user_id=%s AND conversation_uuid=%s",
                        (user_id, conversation_uuid),
                    )
                    deleted = cursor.rowcount > 0
                connection.commit()
                return deleted
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _conversation(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["conversation_uuid"],
            "title": row["title"],
            "messageCount": int(row.get("message_count") or 0),
            "lastMessage": row.get("last_message_preview") or "",
            "createdAt": AiConversationRepository._datetime(row.get("created_at")),
            "updatedAt": AiConversationRepository._datetime(row.get("updated_at")),
        }

    @staticmethod
    def _message(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "role": row["role"],
            "content": row["content"],
            "error": bool(row.get("is_error")),
            "model": row.get("model"),
            "usage": {
                "promptTokens": int(row.get("prompt_tokens") or 0),
                "completionTokens": int(row.get("completion_tokens") or 0),
                "totalTokens": int(row.get("total_tokens") or 0),
            },
            "createdAt": AiConversationRepository._datetime(row.get("created_at")),
        }

    @staticmethod
    def _datetime(value: datetime | None) -> str | None:
        return value.isoformat(timespec="milliseconds") if value else None

ai_conversation_repository = AiConversationRepository()
