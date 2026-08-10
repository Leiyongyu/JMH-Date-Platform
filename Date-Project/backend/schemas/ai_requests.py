from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AiPageContext(BaseModel):
    path: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=200)


class AiConversationCreateRequest(BaseModel):
    title: str = Field(default="新对话", max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return " ".join(value.split())[:200] or "新对话"


class AiChatRequest(BaseModel):
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=4000)
    page_context: AiPageContext | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("消息内容不能为空")
        return content
