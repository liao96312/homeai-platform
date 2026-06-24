from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.api.payloads import rag_log_payload
from backend.app.api.schemas import (
    AgentCancelRequest, AgentDispatchRequest, AgentHandoffRequest,
    AgentResumeRequest, AgentRetryRequest, AgentRunRequest,
)
from backend.app.api.shared import ROLE_AGENT_MAP, pagination
from backend.app.core.config import settings
from backend.app.models.domain import AgentRun, RagQueryLog, User
from backend.app.services.agent_runtime import (
    AGENT_TOOL_CATALOG, LANGGRAPH_AVAILABLE, LANGGRAPH_IMPORT_ERROR,
    agent_run_payload, cancel_agent_run, get_agent_run_or_404,
    list_agent_steps, list_tool_calls, mark_stale_running_runs_failed,
    request_handoff, resume_handoff, run_agent,
)
from backend.app.api.routes._routers import router
from backend.app.api.routes._helpers import add_log
from backend.app.api.routes._wecom_helpers import (
    dispatch_agent_message, format_agent_dispatch_reply,
)


@router.post("/agent/dispatch")
def agent_dispatch(req: AgentDispatchRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run_result = run_agent(
        db,
        user=user,
        text=req.message,
        executor=dispatch_agent_message,
        reply_formatter=format_agent_dispatch_reply,
        channel="web",
        conversation_id=ROLE_AGENT_MAP.get(user.role.key, settings.wecom_default_conversation_key),
        max_attempts=1,
    )
    return {
        "route": run_result.get("route"),
        "tool": run_result.get("toolName"),
        "result": (run_result.get("state") or {}).get("result") or {},
        "reply": run_result.get("output"),
        "run": run_result,
    }


@router.post("/agent/run")
def create_agent_run(req: AgentRunRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = run_agent(
        db,
        user=user,
        text=req.message,
        executor=dispatch_agent_message,
        reply_formatter=format_agent_dispatch_reply,
        channel=req.channel,
        conversation_id=req.conversation_id,
        sender_id=req.sender_id,
        metadata=req.metadata,
        max_attempts=req.max_attempts,
    )
    add_log(db, "🧭", "Agent 编排运行", f"{result['route']} / {result['toolName']} / {result['status']} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    return result


@router.get("/agent/tools")
def list_agent_tools(user: User = Depends(get_current_user)):
    runtime = {
        "name": "langgraph" if LANGGRAPH_AVAILABLE else "fallback",
        "langgraphAvailable": LANGGRAPH_AVAILABLE,
        "required": settings.agent_runtime_required,
        "fallbackReason": "" if LANGGRAPH_AVAILABLE else LANGGRAPH_IMPORT_ERROR,
    }
    if user.role.key == "admin":
        return {"tools": AGENT_TOOL_CATALOG, "runtime": runtime}
    visible_route = ROLE_AGENT_MAP.get(user.role.key)
    visible_routes = {visible_route, "chat"}
    if user.role.key in {"promo", "promo_manager"}:
        visible_routes.add("video")
    return {"tools": [item for item in AGENT_TOOL_CATALOG if item["route"] in visible_routes], "runtime": runtime}


@router.get("/agent/runs")
def list_agent_runs(
    status_filter: str | None = None,
    channel: str | None = None,
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mark_stale_running_runs_failed(db)
    query = select(AgentRun)
    if user.role.key != "admin":
        query = query.where(AgentRun.user_id == user.id)
    if status_filter:
        query = query.where(AgentRun.status == status_filter)
    if channel:
        query = query.where(AgentRun.channel == channel)
    query = query.order_by(AgentRun.id.desc()).limit(max(1, min(limit, 100)))
    runs = db.scalars(query).all()
    return {"runs": [agent_run_payload(item) for item in runs]}


@router.get("/agent/runs/{run_id}")
def get_agent_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = get_agent_run_or_404(db, run_id, user)
    return agent_run_payload(run, steps=list_agent_steps(db, run.id), tool_calls=list_tool_calls(db, run.id))


@router.post("/agent/runs/{run_id}/cancel")
def cancel_run(run_id: int, req: AgentCancelRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = get_agent_run_or_404(db, run_id, user)
    run = cancel_agent_run(db, run, req.reason)
    add_log(db, "⏹️", "取消 Agent Run", f"{run.run_key} · 操作人：{user.full_name}", "red")
    commit_or_rollback(db)
    return agent_run_payload(run, steps=list_agent_steps(db, run.id), tool_calls=list_tool_calls(db, run.id))


@router.post("/agent/runs/{run_id}/retry")
def retry_agent_run(run_id: int, req: AgentRetryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    previous = get_agent_run_or_404(db, run_id, user)
    result = run_agent(
        db,
        user=user,
        text=previous.input_text,
        executor=dispatch_agent_message,
        reply_formatter=format_agent_dispatch_reply,
        channel=previous.channel,
        conversation_id=previous.conversation_id,
        sender_id=previous.sender_id,
        metadata={**((previous.state_json or {}).get("metadata") or {}), "retryOf": previous.id, "retryOfRunKey": previous.run_key},
        max_attempts=req.max_attempts,
    )
    add_log(db, "🔁", "重试 Agent Run", f"{previous.run_key} -> {result['runKey']} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    return result


@router.post("/agent/runs/{run_id}/handoff")
def handoff_run(run_id: int, req: AgentHandoffRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = get_agent_run_or_404(db, run_id, user)
    handoff = request_handoff(db, run, req.reason, req.assigned_to_id)
    add_log(db, "🙋", "Agent 转人工", f"{run.run_key} / {req.reason[:80]} · 操作人：{user.full_name}", "orange")
    commit_or_rollback(db)
    return {
        "run": agent_run_payload(run, steps=list_agent_steps(db, run.id), tool_calls=list_tool_calls(db, run.id)),
        "handoff": {
            "id": handoff.id,
            "status": handoff.status,
            "reason": handoff.reason,
            "assignedToId": handoff.assigned_to_id,
        },
    }


@router.post("/agent/runs/{run_id}/resume")
def resume_run(run_id: int, req: AgentResumeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = get_agent_run_or_404(db, run_id, user)
    decision = {"action": req.action, "response": req.response, "feedback": req.feedback, "operatorId": user.id}
    run = resume_handoff(db, run, decision)
    add_log(db, "▶️", "恢复 Agent Run", f"{run.run_key} / {req.action} · 操作人：{user.full_name}", "green")
    commit_or_rollback(db)
    return agent_run_payload(run, steps=list_agent_steps(db, run.id), tool_calls=list_tool_calls(db, run.id))


@router.get("/rag/query-logs")
def list_rag_query_logs(
    conversation_key: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(RagQueryLog)
    if conversation_key:
        query = query.where(RagQueryLog.conversation_key == conversation_key)
    if user.role.key != "admin":
        query = query.where(RagQueryLog.user_id == user.id)
    safe_limit, safe_offset = pagination(limit, offset)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(RagQueryLog.id.desc()).offset(safe_offset).limit(safe_limit)
    return {"logs": [rag_log_payload(item) for item in db.scalars(query).all()], "total": total, "limit": safe_limit, "offset": safe_offset}


