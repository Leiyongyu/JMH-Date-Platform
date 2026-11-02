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


class AiAgentAccess(BaseModel):
    """Java 网关根据登录用户计算并覆盖写入，前端传入的同名字段不会被采用。"""

    permissions: list[str] = Field(default_factory=list, max_length=5000)
    scopes: dict[str, list[str] | None] = Field(default_factory=dict)


class AiAgentRunRequest(AiChatRequest):
    access: AiAgentAccess = Field(default_factory=AiAgentAccess)


class AiAgentFeedbackRequest(BaseModel):
    rating: int = Field(..., description="1=有帮助，-1=没帮助")
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("rating")
    @classmethod
    def _rating(cls, value: int) -> int:
        if value not in (1, -1):
            raise ValueError("rating 只能是 1 或 -1")
        return value


class AiBriefRunRequest(BaseModel):
    access: AiAgentAccess = Field(default_factory=AiAgentAccess)
    force: bool = Field(default=False, description="true=手动立即运行，不检查是否到期")
