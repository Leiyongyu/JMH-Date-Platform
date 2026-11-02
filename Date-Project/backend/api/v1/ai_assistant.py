from __future__ import annotations

from typing import NamedTuple
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from backend.api.deps import require_internal_access
from backend.schemas.ai_requests import AiAgentRunRequest, AiChatRequest, AiConversationCreateRequest
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


# ---------------------------------------------------------------- 数据助手（工具调用）

@router.post("/agent-runs", status_code=202)
async def create_agent_run(
    payload: AiAgentRunRequest,
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    """后台执行一次数据助手任务，立即返回 runId；进度与结果用 GET /agent-runs/{runId} 轮询。"""
    from backend.agent.context import AgentAccess, AgentContext
    from backend.agent.llm import current_provider
    from backend.agent.runner import start_run

    provider = current_provider()
    if not provider.api_key:
        raise HTTPException(status_code=503, detail=f"AI助手尚未配置，请在Python服务中设置 {provider.key_env}")
    conversation_id = str(payload.conversation_id)
    # 先确认会话属于当前用户，避免后台任务写入他人会话。
    await run_in_threadpool(ai_assistant_service.get_conversation, identity.user_id, conversation_id)
    context = AgentContext(
        user_id=identity.user_id, username=identity.username,
        access=AgentAccess.from_payload(payload.access.model_dump()),
        request_id=request.state.request_id,
    )
    page = payload.page_context.model_dump() if payload.page_context else None
    run_id = await start_run(context, conversation_id, payload.message, page)
    return success_response({"runId": run_id, "status": "running"}, request_id=request.state.request_id)


@router.get("/agent-runs/{run_id}")
async def get_agent_run(
    run_id: UUID,
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    from backend.repositories import ai_agent_repository

    run = await run_in_threadpool(ai_agent_repository.get_run, identity.user_id, str(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在或无权访问")
    return success_response(run, request_id=request.state.request_id)


@router.get("/memories")
async def list_agent_memories(
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    from backend.repositories import ai_agent_repository

    memories = await run_in_threadpool(ai_agent_repository.list_memories, identity.user_id)
    return success_response(memories, request_id=request.state.request_id)


@router.delete("/memories/{memory_id}")
async def delete_agent_memory(
    memory_id: int,
    request: Request,
    identity: ErpUserIdentity = Depends(require_erp_user),
):
    from backend.repositories import ai_agent_repository

    if not await run_in_threadpool(ai_agent_repository.delete_memory, identity.user_id, memory_id):
        raise HTTPException(status_code=404, detail="记忆不存在或无权访问")
    return success_response({"id": memory_id, "deleted": True}, request_id=request.state.request_id)

