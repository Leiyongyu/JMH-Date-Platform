from __future__ import annotations

from typing import NamedTuple
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from backend.api.deps import require_internal_access
from backend.schemas.ai_requests import AiChatRequest, AiConversationCreateRequest
from backend.schemas.responses import success_response
from backend.services.ai_assistant_service import ai_assistant_service


class ErpUserIdentity(NamedTuple):
    user_id: int
    username: str


def require_erp_user(
    user_id: int | None = Header(default=None, alias="X-Erp-User-ID"),
    username: str | None = Header(default=None, alias="X-Erp-User"),
) -> ErpUserIdentity:
    normalized_username = (username or "").strip()
    if not user_id or user_id <= 0 or not normalized_username:
        raise HTTPException(status_code=400, detail="缺少有效的ERP用户身份")
    return ErpUserIdentity(user_id=user_id, username=normalized_username[:100])


router = APIRouter(
    prefix="/api/v1/ai-assistant",
    dependencies=[Depends(require_internal_access)],
)


@router.get("/status")
def get_ai_assistant_status(request: Request):
    return success_response(
        ai_assistant_service.status(),
        request_id=request.state.request_id,
    )


@router.get("/conversations")
def list_ai_conversations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    return success_response(
        ai_assistant_service.list_conversations(identity.user_id, limit),
        request_id=request.state.request_id,
    )


@router.post("/conversations")
def create_ai_conversation(
    payload: AiConversationCreateRequest,
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    return success_response(
        ai_assistant_service.create_conversation(
            identity.user_id, identity.username, payload.title
        ),
        request_id=request.state.request_id,
    )


@router.get("/conversations/{conversation_id}")
def get_ai_conversation(
    conversation_id: UUID,
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    return success_response(
        ai_assistant_service.get_conversation(identity.user_id, str(conversation_id)),
        request_id=request.state.request_id,
    )


@router.delete("/conversations/{conversation_id}")
def delete_ai_conversation(
    conversation_id: UUID,
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    ai_assistant_service.delete_conversation(identity.user_id, str(conversation_id))
    return success_response(
        {"id": str(conversation_id), "deleted": True},
        request_id=request.state.request_id,
    )


@router.post("/chats")
async def create_ai_chat(
    payload: AiChatRequest,
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    result = await ai_assistant_service.chat(
        payload, identity.user_id, identity.username, request.state.request_id
    )
    return success_response(result, request_id=request.state.request_id)
