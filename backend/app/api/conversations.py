from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.api.shared import ROLE_AGENT_MAP, assert_agent_access, user_payload
from backend.app.db.session import get_db
from backend.app.models.domain import Conversation, User
from backend.app.api.payloads import conversation_payload


router = APIRouter(prefix="/api")


@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conversations_query = select(Conversation).order_by(Conversation.id)
    if user.role.key != "admin":
        agent_key = ROLE_AGENT_MAP.get(user.role.key)
        if not agent_key:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色未绑定 AI 助手")
        conversations_query = conversations_query.where(Conversation.key == agent_key)
    conversations = db.scalars(conversations_query).all()
    return {
        "currentUser": user_payload(user),
        "conversations": [conversation_payload(conversation) for conversation in conversations],
    }


@router.get("/conversations/{conversation_key}")
def get_conversation(conversation_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_agent_access(user, conversation_key)
    conversation = db.scalar(select(Conversation).where(Conversation.key == conversation_key))
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conversation_payload(conversation)
