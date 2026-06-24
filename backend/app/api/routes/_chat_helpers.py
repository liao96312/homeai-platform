from backend.app.db.session import commit_or_rollback
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.domain import Conversation, ConversationMessage
from backend.app.services.chat import ChatCompletionRequest


def latest_user_message(req: ChatCompletionRequest) -> str:
    for message in reversed(req.messages):
        if message.role == "user":
            return extract_chat_content(message.content)
    return ""


def extract_chat_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item.get("text", "")))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return "" if content is None else str(content)


def assistant_reply_from_completion(completion: dict) -> str:
    choices = completion.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def persist_conversation_messages(
    db: Session,
    conversation_key: str | None,
    user_message: str,
    assistant_reply: str,
    rag: dict | None = None,
) -> None:
    if not conversation_key or not user_message.strip() or not assistant_reply.strip():
        return
    conversation = db.scalar(select(Conversation).where(Conversation.key == conversation_key))
    if not conversation:
        return
    db.add_all(
        [
            ConversationMessage(
                conversation_id=conversation.id,
                sender="me",
                message_type="text",
                content=user_message.strip(),
            ),
            ConversationMessage(
                conversation_id=conversation.id,
                sender="ai",
                message_type="text",
                content=assistant_reply.strip(),
                extra_json={"rag": rag or None},
            ),
        ]
    )
    conversation.preview = assistant_reply.strip()[:120]
    conversation.time_label = "刚刚"
    conversation.unread = 0
    commit_or_rollback(db)

