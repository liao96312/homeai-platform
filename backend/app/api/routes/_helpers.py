import time
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.payloads import normalize_top_sources, percent
from backend.app.api.shared import ROLE_PERMISSION_ALIASES
from backend.app.models.domain import (
    Agent, AgentRun, BusinessArtifact, OperationLog, PromoTemplate, PublishJob, RagQueryLog, SystemConfig, User, WecomWebhookEvent,
)
from backend.app.services.publishing import build_multipost_task, publish_via_multipost, resolve_platform_code

CONFIG_CACHE_TTL_SECONDS = 10
_CONFIG_ENABLED_CACHE: dict[str, tuple[float, bool]] = {}
_CONFIG_ENABLED_CACHE_LOCK = Lock()
SIMPLE_ARTIFACT_STATUSES = {"draft", "confirmed", "completed", "archived"}
LEGACY_ARTIFACT_STATUS_MAP = {
    "pending_review": "confirmed",
    "pending": "confirmed",
    "assigned": "confirmed",
}


def assert_admin(user: User) -> None:
    if user.role.key != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")


def add_log(db: Session, icon: str, title: str, detail: str, theme: str = "blue") -> None:
    db.add(OperationLog(icon=icon, title=title, detail=detail, time_label="刚刚", theme=theme))


def get_artifact_or_404(db: Session, artifact_id: int, user: User) -> BusinessArtifact:
    artifact = db.scalar(select(BusinessArtifact).where(BusinessArtifact.id == artifact_id))
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="业务产物不存在")
    if user.role.key != "admin" and artifact.owner_id != user.id and not can_access_design_artifact(artifact, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该业务产物")
    return artifact


def can_access_design_artifact(artifact: BusinessArtifact, user: User) -> bool:
    if artifact.artifact_type != "design_card":
        return False
    if user.role.key == "design_manager":
        return True
    if user.role.key != "designer":
        return False
    assignment = (artifact.result_json or {}).get("assignment") if isinstance(artifact.result_json, dict) else {}
    return int(assignment.get("assignedDesignerId") or 0) == user.id


def assert_design_workflow_access(user: User) -> None:
    require_roles(user, {"designer"})


def get_owned_artifact_or_404(db: Session, artifact_id: int, user: User) -> BusinessArtifact:
    query = select(BusinessArtifact).where(BusinessArtifact.id == artifact_id)
    if user.role.key != "admin":
        query = query.where(BusinessArtifact.owner_id == user.id)
    artifact = db.scalar(query)
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="业务产物不存在")
    return artifact


def get_promo_template_or_404(db: Session, template_id: int, user: User) -> PromoTemplate:
    template = db.scalar(select(PromoTemplate).where(PromoTemplate.id == template_id))
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推广模板不存在")
    if user.role.key != "admin" and template.owner_id not in {None, user.id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该推广模板")
    return template


def normalize_artifact_status(status_text: str) -> str:
    return LEGACY_ARTIFACT_STATUS_MAP.get(status_text, status_text)


def validate_artifact_status(status_text: str) -> str:
    normalized = normalize_artifact_status(status_text)
    if normalized not in SIMPLE_ARTIFACT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="业务产物状态不合法")
    return normalized


def save_artifact(
    db: Session,
    artifact_type: str,
    title: str,
    source: str,
    result: dict,
    user: User,
    status_text: str = "draft",
) -> BusinessArtifact:
    artifact = BusinessArtifact(
        artifact_type=artifact_type,
        title=title[:160],
        status=validate_artifact_status(status_text),
        owner_id=user.id,
        source=source,
        result_json=result,
        created_at_label="刚刚",
    )
    db.add(artifact)
    db.flush()
    return artifact


def get_publish_job_or_404(db: Session, job_id: int, user: User) -> PublishJob:
    job = db.scalar(select(PublishJob).where(PublishJob.id == job_id))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发布任务不存在")
    if user.role.key != "admin" and job.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该发布任务")
    return job


def persist_publish_job(
    db: Session,
    *,
    artifact: BusinessArtifact | None,
    user: User,
    platform: str,
    title: str,
    content: str,
    tags: list[str],
    scheduled_at: datetime | None = None,
) -> PublishJob:
    normalized_schedule = normalize_datetime(scheduled_at) if scheduled_at else None
    if normalized_schedule and normalized_schedule > datetime.now(timezone.utc):
        platform_code = resolve_platform_code(platform)
        request_payload = build_multipost_task(title, content, platform_code, tags)
        request_payload["scheduledAt"] = normalized_schedule.isoformat()
        provider = "multipost"
        status_text = "scheduled"
        external_task_id = ""
        response_payload = {}
        error_text = ""
    else:
        result = publish_via_multipost(title=title, content=content, platform_label=platform, tags=tags)
        provider = result.provider
        platform_code = result.platform_code
        status_text = result.status
        external_task_id = result.external_task_id
        request_payload = result.request_payload or {}
        response_payload = result.response_payload or {}
        error_text = result.error
    job = PublishJob(
        artifact_id=artifact.id if artifact else None,
        user_id=user.id,
        provider=provider,
        platform_label=platform,
        platform_code=platform_code,
        status=status_text,
        external_task_id=external_task_id,
        title=title[:160],
        content=content,
        request_json=request_payload,
        response_json=response_payload,
        error=error_text,
        scheduled_at=normalized_schedule,
        created_at_label="刚刚",
        updated_at_label="刚刚",
    )
    db.add(job)
    db.flush()
    return job


def config_enabled(db: Session, key: str, default: bool = True) -> bool:
    now = time.monotonic()
    with _CONFIG_ENABLED_CACHE_LOCK:
        cached = _CONFIG_ENABLED_CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]
    config = db.scalar(select(SystemConfig).where(SystemConfig.key == key))
    enabled = default if config is None else bool(config.enabled)
    with _CONFIG_ENABLED_CACHE_LOCK:
        _CONFIG_ENABLED_CACHE[key] = (now + CONFIG_CACHE_TTL_SECONDS, enabled)
    return enabled


def clear_config_enabled_cache(key: str | None = None) -> None:
    with _CONFIG_ENABLED_CACHE_LOCK:
        if key is None:
            _CONFIG_ENABLED_CACHE.clear()
        else:
            _CONFIG_ENABLED_CACHE.pop(key, None)


def knowledge_hit_rate(db: Session, kb_key: str) -> str:
    return knowledge_hit_rates(db, [kb_key]).get(kb_key, "0%")


def knowledge_hit_rates(db: Session, kb_keys: list[str]) -> dict[str, str]:
    key_set = set(kb_keys)
    stats = {key: {"total": 0, "hits": 0} for key in key_set}
    logs = db.scalars(select(RagQueryLog).order_by(RagQueryLog.id.desc()).limit(500)).all()
    for log in logs:
        top_sources = normalize_top_sources(log.top_sources)
        related_keys = set()
        if log.conversation_key in key_set:
            related_keys.add(log.conversation_key)
        related_keys.update(source.get("kbKey") for source in top_sources if source.get("kbKey") in key_set)
        for key in related_keys:
            stats[key]["total"] += 1
            if (log.hit_count or 0) > 0 or any(source.get("kbKey") == key and source.get("type") != "status" for source in top_sources):
                stats[key]["hits"] += 1
    return {
        key: f"{round((item['hits'] / item['total']) * 100)}%" if item["total"] else "0%"
        for key, item in stats.items()
    }

def weekly_usage_payload(db: Session, now: datetime | None = None) -> list[dict]:
    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    buckets = {day: {"day": day, "sales": 0, "design": 0, "promo": 0} for day in days}
    agent_keys = {"sales", "design", "promo"}
    now = now or datetime.now(timezone.utc)
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    rag_logs = db.scalars(
        select(RagQueryLog)
        .where(RagQueryLog.created_at >= start_of_week)
        .order_by(RagQueryLog.created_at.asc())
    ).all()
    for log in rag_logs:
        key = log.conversation_key if log.conversation_key in agent_keys else None
        if not key:
            continue
        created_at = log.created_at if isinstance(log.created_at, datetime) else normalize_datetime(log.created_at)
        day = days[created_at.weekday()]
        buckets[day][key] += 1

    wecom_events = db.scalars(
        select(WecomWebhookEvent)
        .where(WecomWebhookEvent.created_at >= start_of_week)
        .order_by(WecomWebhookEvent.created_at.asc())
    ).all()
    for event in wecom_events:
        key = event.conversation_key if event.conversation_key in agent_keys else None
        if not key:
            continue
        created_at = event.created_at if isinstance(event.created_at, datetime) else normalize_datetime(event.created_at)
        day = days[created_at.weekday()]
        buckets[day][key] += 1

    return [buckets[day] for day in days]


def estimate_agent_cost(run: AgentRun) -> float:
    """Rough cost estimate based on text length.

    The previous formula divided total chars by 2, which roughly matches English
    (~4 chars/token) but under-estimates Chinese text by ~2x (CJK chars are
    ~1 token each). Use a charset-aware heuristic and the DeepSeek chat blended
    price (~¥0.0015 / 1K tokens for mixed in/out).
    """
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        cjk = 0
        ascii_count = 0
        other = 0
        for ch in text:
            cp = ord(ch)
            if 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF:
                cjk += 1
            elif ch.isascii() and not ch.isspace():
                ascii_count += 1
            elif not ch.isspace():
                other += 1
        # CJK: ~1 token/char; ASCII: ~4 chars/token; other: ~1.5 chars/token
        return cjk + ascii_count // 4 + max(0, other * 2 // 3)

    estimated_tokens = max(1, _estimate_tokens(run.input_text or "") + _estimate_tokens(run.output_text or ""))
    return estimated_tokens / 1000 * 0.0015


class _AgentRunLite:
    """Lightweight stand-in for AgentRun carrying only the fields used by
    estimate_agent_cost — avoids materializing full ORM rows for cost calc."""

    __slots__ = ("input_text", "output_text")

    def __init__(self, input_text: str | None, output_text: str | None):
        self.input_text = input_text
        self.output_text = output_text


def business_insights_payload(db: Session, user: User) -> dict:
    """Aggregated business KPIs for the dashboard.

    Previously this loaded up to 3000 rows (1000 artifacts + 1000 agent runs +
    1000 RAG logs) into Python memory and filtered with list comprehensions.
    Now most counts are pushed down to SQL aggregates; only the few rows that
    need JSON inspection (lead_score grade/score, RAG top_sources) are loaded,
    and they are bounded to a recent window.
    """
    is_admin = user.role.key == "admin"
    artifact_filters = [] if is_admin else [BusinessArtifact.owner_id == user.id]
    run_filters = [] if is_admin else [AgentRun.user_id == user.id]
    rag_filters = [] if is_admin else [RagQueryLog.user_id == user.id]

    def _count_artifact(artifact_type: str, statuses: set[str] | None = None) -> int:
        conditions = [BusinessArtifact.artifact_type == artifact_type, *artifact_filters]
        if statuses:
            conditions.append(BusinessArtifact.status.in_(statuses))
        return db.scalar(select(func.count()).select_from(BusinessArtifact).where(*conditions)) or 0

    lead_cards_total = _count_artifact("lead_score")
    design_cards_total = _count_artifact("design_card")
    promo_items_total = _count_artifact("promo_copy")
    total_artifacts = db.scalar(select(func.count()).select_from(BusinessArtifact).where(*artifact_filters)) or 0

    confirmed_leads = _count_artifact("lead_score", {"confirmed", "assigned", "completed"})
    assigned_design_cards = _count_artifact("design_card", {"assigned", "completed"})
    publish_ready = _count_artifact("promo_copy", {"confirmed", "pending", "completed"})

    def _count_runs(statuses: set[str] | None = None) -> int:
        conditions = list(run_filters)
        if statuses:
            conditions.append(AgentRun.status.in_(statuses))
        return db.scalar(select(func.count()).select_from(AgentRun).where(*conditions)) or 0

    total_runs = _count_runs()
    completed_runs = _count_runs({"completed"})
    failed_runs = _count_runs({"failed"})
    waiting_runs = _count_runs({"waiting_human"})

    # high_value_leads needs JSON inspection (grade / score) — load only
    # lead_score artifacts instead of all 1000 mixed-type artifacts.
    lead_cards = db.scalars(
        select(BusinessArtifact).where(
            BusinessArtifact.artifact_type == "lead_score",
            *artifact_filters,
        )
    ).all()
    high_value_leads = [
        item
        for item in lead_cards
        if (item.result_json or {}).get("grade") in {"A", "B"} or int((item.result_json or {}).get("score") or 0) >= 55
    ]

    # Estimated cost: load only id + text fields for runs, bounded to recent 500
    # to avoid pulling the full table when the deployment has been running long.
    runs_for_cost = db.execute(
        select(AgentRun.input_text, AgentRun.output_text).where(*run_filters).order_by(AgentRun.id.desc()).limit(500)
    ).all()
    estimated_cost = sum(estimate_agent_cost(_AgentRunLite(input_text=row[0], output_text=row[1])) for row in runs_for_cost)

    # RAG triad counts need to inspect top_sources JSON — bound to recent 500 logs.
    rag_logs = db.scalars(
        select(RagQueryLog).where(*rag_filters).order_by(RagQueryLog.id.desc()).limit(500)
    ).all()
    rag_total = db.scalar(select(func.count()).select_from(RagQueryLog).where(*rag_filters)) or 0
    rag_hits = 0
    rag_maybe = 0
    rag_misses = 0
    for log in rag_logs:
        top_sources = normalize_top_sources(log.top_sources)
        status_payload = (top_sources[0] or {}).get("ragStatus") if top_sources else None
        status_code = (status_payload or {}).get("code")
        if status_code == "hit":
            rag_hits += 1
        elif status_code == "maybe":
            rag_maybe += 1
        else:
            rag_misses += 1

    return {
        "sales": {
            "totalLeads": lead_cards_total,
            "highValueLeads": len(high_value_leads),
            "confirmedLeads": confirmed_leads,
            "conversionRate": percent(confirmed_leads, lead_cards_total),
            "highIntentRate": percent(len(high_value_leads), lead_cards_total),
        },
        "design": {
            "totalCards": design_cards_total,
            "assignedCards": assigned_design_cards,
            "assignmentRate": percent(assigned_design_cards, design_cards_total),
        },
        "content": {
            "promoCopies": promo_items_total,
            "publishReady": publish_ready,
            "readyRate": percent(publish_ready, promo_items_total),
        },
        "rag": {
            "totalQueries": rag_total,
            "hits": rag_hits,
            "maybes": rag_maybe,
            "misses": rag_misses,
            "hitRate": percent(rag_hits, rag_total),
            "reviewRate": percent(rag_maybe, rag_total),
        },
        "agent": {
            "totalRuns": total_runs,
            "completedRuns": completed_runs,
            "failedRuns": failed_runs,
            "waitingHuman": waiting_runs,
            "successRate": percent(completed_runs, total_runs),
            "estimatedCost": f"¥{estimated_cost:.2f}",
        },
        "summary": [
            {"label": "业务产物", "value": total_artifacts, "hint": "销售/设计/推广累计产出"},
            {"label": "待人工", "value": waiting_runs, "hint": "Agent 等待人工接管"},
            {"label": "知识库命中", "value": percent(rag_hits, rag_total), "hint": "RAG Triad 已命中占比"},
            {"label": "估算成本", "value": f"¥{estimated_cost:.2f}", "hint": "按字符折算 token 的粗估值"},
        ],
    }


def normalize_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def assert_agent_online(db: Session, conversation_key: str | None) -> None:
    if not conversation_key:
        return
    agent = db.scalar(select(Agent).where(Agent.key == conversation_key))
    if agent and agent.status != "online":
        label = {"paused": "已暂停", "maintenance": "维护中"}.get(agent.status, agent.status)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{agent.name}{label}，暂时不能调用")


def require_roles(user: User, allowed: set[str]) -> None:
    expanded = set()
    for role_key in allowed:
        expanded.update(ROLE_PERMISSION_ALIASES.get(role_key, {role_key}))
    if user.role.key != "admin" and user.role.key not in expanded:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权使用该业务工具")

