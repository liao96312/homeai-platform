import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.shared import CANONICAL_KB_ORDER
from backend.app.models.domain import (
    Agent,
    BusinessArtifact,
    Conversation,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeBase,
    PromoTemplate,
    PublishJob,
    RagQueryLog,
    Role,
    User,
    WecomWebhookEvent,
)


def normalize_artifact_status(status_text: str) -> str:
    return {
        "pending_review": "confirmed",
        "pending": "confirmed",
        "assigned": "confirmed",
    }.get(status_text, status_text)


def artifact_payload(item: BusinessArtifact) -> dict:
    result = item.result_json or {}
    assignment = result.get("assignment") if isinstance(result, dict) else None
    if isinstance(assignment, dict):
        assignment = {**assignment, "status": normalize_artifact_status(str(assignment.get("status") or item.status))}
    return {
        "id": item.id,
        "type": item.artifact_type,
        "title": item.title,
        "status": normalize_artifact_status(item.status),
        "rawStatus": item.status,
        "source": item.source,
        "result": result,
        "assignment": assignment or None,
        "createdAt": item.created_at_label,
        "owner": item.owner.full_name if item.owner else "",
    }


def publish_job_payload(job: PublishJob) -> dict:
    return {
        "id": job.id,
        "artifactId": job.artifact_id,
        "provider": job.provider,
        "platform": job.platform_label,
        "platformCode": job.platform_code,
        "status": job.status,
        "externalTaskId": job.external_task_id,
        "title": job.title,
        "content": job.content,
        "request": job.request_json,
        "response": job.response_json,
        "error": job.error,
        "scheduledAt": job.scheduled_at.isoformat() if job.scheduled_at else "",
        "createdAt": job.created_at_label,
        "updatedAt": job.updated_at_label,
    }


def promo_template_payload(item: PromoTemplate) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "platform": item.platform,
        "scene": item.scene,
        "prompt": item.prompt,
        "defaultAudience": item.default_audience,
        "defaultTone": item.default_tone,
        "defaultSellingPoints": item.default_selling_points or [],
        "isActive": item.is_active,
        "createdAt": item.created_at.isoformat() if item.created_at else "",
        "owner": item.owner.full_name if item.owner else "",
    }


def design_assignee_payload(user: User) -> dict:
    return {"id": user.id, "username": user.username, "fullName": user.full_name, "role": user.role.key}


def normalize_top_sources(top_sources) -> list[dict]:
    if isinstance(top_sources, str):
        try:
            top_sources = json.loads(top_sources)
        except json.JSONDecodeError:
            top_sources = []
    return top_sources or []


def role_payload(db: Session, role: Role) -> dict:
    user_count = db.scalar(select(func.count(User.id)).where(User.role_id == role.id, User.is_active)) or 0
    return {"key": role.key, "name": role.name, "color": role.color, "user_count": user_count}


def rag_log_payload(item: RagQueryLog) -> dict:
    top_sources = normalize_top_sources(item.top_sources)
    hit_count = int(item.hit_count or 0)
    rag_status = None
    if top_sources:
        rag_status = top_sources[0].get("ragStatus")
    return {
        "id": item.id,
        "conversationKey": item.conversation_key,
        "query": item.query,
        "topK": item.top_k,
        "hitCount": hit_count,
        "injected": bool(item.injected and hit_count > 0),
        "ragStatus": rag_status,
        "topSources": top_sources or [],
        "createdAt": item.created_at_label,
        "user": item.user.full_name if item.user else "",
    }


def agent_payload(db: Session, agent: Agent) -> dict:
    calls_today = db.scalar(
        select(func.count(WecomWebhookEvent.id)).where(
            WecomWebhookEvent.conversation_key == agent.key,
            WecomWebhookEvent.status == "replied",
        )
    ) or 0
    return {
        "key": agent.key,
        "name": agent.name,
        "icon": agent.icon,
        "theme": agent.theme,
        "status": agent.status,
        "calls_today": calls_today,
        "success_rate": agent.success_rate,
        "avg_latency": agent.avg_latency,
    }


def conversation_payload(conversation: Conversation) -> dict:
    row_messages = [
        {
            "sender": item.sender,
            "type": item.message_type,
            "content": item.content,
            **(item.extra_json or {}),
        }
        for item in getattr(conversation, "message_rows", [])[-80:]
    ]
    return {
        "key": conversation.key,
        "name": conversation.name,
        "assistant_name": conversation.assistant_name,
        "icon": conversation.icon,
        "theme": conversation.theme,
        "preview": conversation.preview,
        "time_label": conversation.time_label,
        "unread": conversation.unread,
        "quick_actions": conversation.quick_actions,
        "messages": row_messages or conversation.messages,
    }


def percent(numerator: int | float, denominator: int | float) -> str:
    if not denominator:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"


def kb_payload(db: Session, kb: KnowledgeBase, hit_rates: dict[str, str] | None = None) -> dict:
    docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
    chunks = db.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.kb_id == kb.id)) or 0
    hit_rate = (hit_rates or {}).get(kb.key) or "0%"
    return {
        "key": kb.key,
        "name": kb.name,
        "description": kb.description,
        "icon": kb.icon,
        "theme": kb.theme,
        "docs": docs,
        "chunks": chunks,
        "hit_rate": hit_rate,
        "updated_at_label": kb.updated_at_label,
        "isSystem": kb.key in CANONICAL_KB_ORDER,
    }
