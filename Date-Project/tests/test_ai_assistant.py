from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.ai_requests import AiChatRequest, AiPageContext
from backend.services.ai_assistant_service import ai_assistant_service


def test_ai_chat_request_requires_conversation_and_message() -> None:
    with pytest.raises(ValidationError):
        AiChatRequest.model_validate({"message": "你好"})


def test_ai_chat_payload_keeps_rules_on_server() -> None:
    messages = [{"role": "user", "content": "你好"}]
    page_context = AiPageContext.model_validate(
        {"path": "/index", "title": "首页"}
    )

    payload = ai_assistant_service._build_payload(messages, page_context)

    assert payload["messages"][0]["role"] == "system"
    assert "首页" in payload["messages"][0]["content"]
    assert payload["messages"][-1] == {"role": "user", "content": "你好"}
    assert payload["stream"] is False


def test_ai_status_does_not_expose_api_key() -> None:
    status = ai_assistant_service.status()

    assert "apiKey" not in status
    assert "api_key" not in status
    assert status["provider"] == "deepseek"
