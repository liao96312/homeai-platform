from fastapi import Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.api.schemas import ChatRequest
from backend.app.api.shared import assert_agent_access
from backend.app.models.domain import User
from backend.app.services.chat import (
    ChatCompletionRequest, ChatMessage, create_chat_completion,
    create_deepseek_chat_completion_async,
    create_deepseek_chat_completion_stream,
)
from backend.app.api.routes._routers import openai_router, router
from backend.app.api.routes._helpers import add_log, assert_agent_online, config_enabled
from backend.app.api.routes._chat_helpers import (
    assistant_reply_from_completion, latest_user_message, persist_conversation_messages,
)


@router.post("/chat/completions")
@openai_router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conversation_key = (req.metadata or {}).get("conversation_key")
    assert_agent_access(user, conversation_key)
    assert_agent_online(db, conversation_key)
    add_log(
        db,
        "🤖",
        "AI 聊天调用",
        f"{conversation_key or 'openai'} / {req.model} / stream={bool(req.stream)} · 操作人：{user.full_name}",
        "blue",
    )
    commit_or_rollback(db)
    archive_enabled = config_enabled(db, "chat_archive", True)
    safety_enabled = config_enabled(db, "ai_safety_review", True)
    if req.stream:
        def persist_stream_turn(user_message: str, assistant_reply: str) -> None:
            if archive_enabled:
                persist_conversation_messages(db, conversation_key, user_message, assistant_reply)

        return StreamingResponse(
            create_deepseek_chat_completion_stream(
                req,
                conversation_key=conversation_key,
                db=db,
                user_id=str(user.id),
                save_memory=archive_enabled,
                safety_review=safety_enabled,
                on_complete=persist_stream_turn,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    completion = await create_deepseek_chat_completion_async(
        req,
        conversation_key=conversation_key,
        db=db,
        user_id=str(user.id),
        save_memory=archive_enabled,
        safety_review=safety_enabled,
    )
    if archive_enabled:
        persist_conversation_messages(
            db,
            conversation_key,
            latest_user_message(req),
            assistant_reply_from_completion(completion),
            (completion.get("metadata") or {}).get("rag"),
        )
    return completion


@router.post("/chat")
def chat(req: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_agent_access(user, req.conversation_key)
    assert_agent_online(db, req.conversation_key)
    add_log(db, "🤖", "AI 聊天调用", f"{req.conversation_key} / {req.model} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    archive_enabled = config_enabled(db, "chat_archive", True)
    completion = create_chat_completion(
        ChatCompletionRequest(model=req.model, messages=[ChatMessage(role="user", content=req.message)], metadata={"conversation_key": req.conversation_key}),
        role_key=user.role.key,
        conversation_key=req.conversation_key,
        db=db,
        user_id=str(user.id),
        save_memory=archive_enabled,
        safety_review=config_enabled(db, "ai_safety_review", True),
    )
    content = completion["choices"][0]["message"]["content"]
    if archive_enabled:
        persist_conversation_messages(
            db,
            req.conversation_key,
            req.message,
            content,
            (completion.get("metadata") or {}).get("rag"),
        )
    return {"conversationKey": req.conversation_key, "reply": content, "type": "text", "openai": completion}


