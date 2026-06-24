from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import commit_or_rollback
from backend.app.models.domain import AgentHandoff, AgentRun, AgentStep, AgentToolCall, User

logger = logging.getLogger(__name__)
STALE_RUNNING_RUN_MINUTES = 30


def create_agent_run(
    db: Session,
    *,
    user: User,
    text: str,
    channel: str = "web",
    conversation_id: str = "",
    sender_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> AgentRun:
    run = AgentRun(
        run_key=f"run_{uuid.uuid4().hex[:18]}",
        channel=channel,
        conversation_id=conversation_id,
        sender_id=sender_id or str(user.id),
        user_id=user.id,
        status="running",
        input_text=text.strip(),
        state_json={"metadata": metadata or {}, "events": []},
    )
    db.add(run)
    commit_or_rollback(db)
    db.refresh(run)
    return run


def add_agent_step(db: Session, run: AgentRun, name: str, status_text: str = "completed", detail: dict[str, Any] | None = None) -> AgentStep:
    step = AgentStep(run_id=run.id, name=name, status=status_text, detail_json=detail or {})
    db.add(step)
    commit_or_rollback(db)
    db.refresh(step)
    return step


def add_tool_call(
    db: Session,
    run: AgentRun,
    *,
    tool_name: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any] | None = None,
    status_text: str = "completed",
    error: str = "",
) -> AgentToolCall:
    call = AgentToolCall(
        run_id=run.id,
        tool_name=tool_name,
        status=status_text,
        input_json=input_data,
        output_json=output_data or {},
        error=error,
    )
    db.add(call)
    commit_or_rollback(db)
    db.refresh(call)
    return call


def reset_failed_transaction(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        logger.exception("Failed to rollback agent executor transaction")


def mark_agent_run_failed(db: Session, run: AgentRun, error: str) -> None:
    run.status = "failed"
    run.error = error[:2000]
    run.updated_at = datetime.now(timezone.utc)
    commit_or_rollback(db)
    add_agent_step(db, run, "failed", "failed", {"error": run.error})


def mark_stale_running_runs_failed(db: Session, older_than_minutes: int = STALE_RUNNING_RUN_MINUTES) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, older_than_minutes))
    stale_runs = db.scalars(
        select(AgentRun).where(
            AgentRun.status == "running",
            AgentRun.updated_at < cutoff,
        )
    ).all()
    for run in stale_runs:
        run.status = "failed"
        run.error = "agent_run_timeout"
        run.updated_at = datetime.now(timezone.utc)
        db.add(AgentStep(run_id=run.id, name="timeout_cleanup", status="failed", detail_json={"error": run.error}))
    if stale_runs:
        commit_or_rollback(db)
    return len(stale_runs)


def cancel_agent_run(db: Session, run: AgentRun, reason: str = "") -> AgentRun:
    if run.status in {"completed", "failed", "cancelled"}:
        return run
    run.status = "cancelled"
    run.error = reason[:2000]
    run.updated_at = datetime.now(timezone.utc)
    commit_or_rollback(db)
    add_agent_step(db, run, "cancelled", "cancelled", {"reason": reason})
    db.refresh(run)
    return run


def request_handoff(db: Session, run: AgentRun, reason: str, assigned_to_id: int | None = None) -> AgentHandoff:
    run.status = "waiting_human"
    run.updated_at = datetime.now(timezone.utc)
    handoff = AgentHandoff(run_id=run.id, status="pending", reason=reason[:2000], assigned_to_id=assigned_to_id)
    db.add(handoff)
    commit_or_rollback(db)
    add_agent_step(db, run, "human_handoff", "pending", {"reason": reason, "assignedToId": assigned_to_id})
    db.refresh(handoff)
    return handoff


def resume_handoff(db: Session, run: AgentRun, decision: dict[str, Any]) -> AgentRun:
    handoff = db.scalar(
        select(AgentHandoff)
        .where(AgentHandoff.run_id == run.id, AgentHandoff.status == "pending")
        .order_by(AgentHandoff.id.desc())
    )
    if not handoff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有待处理的人工接管")
    action = str(decision.get("action") or "approved")
    handoff.status = action
    handoff.decision_json = decision
    handoff.updated_at = datetime.now(timezone.utc)
    run.status = "completed" if action in {"approved", "responded"} else "cancelled"
    if decision.get("response"):
        run.output_text = str(decision["response"])
    run.updated_at = datetime.now(timezone.utc)
    commit_or_rollback(db)
    add_agent_step(db, run, "human_resume", "completed", {"decision": decision})
    db.refresh(run)
    return run


def get_agent_run_or_404(db: Session, run_id: int, user: User) -> AgentRun:
    query = select(AgentRun).where(AgentRun.id == run_id)
    if user.role.key != "admin":
        query = query.where(AgentRun.user_id == user.id)
    run = db.scalar(query)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Run 不存在")
    return run


def list_agent_steps(db: Session, run_id: int) -> list[AgentStep]:
    return list(db.scalars(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.id)).all())


def list_tool_calls(db: Session, run_id: int) -> list[AgentToolCall]:
    return list(db.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.id)).all())


def agent_run_payload(run: AgentRun, steps: list[AgentStep] | None = None, tool_calls: list[AgentToolCall] | None = None) -> dict[str, Any]:
    return {
        "id": run.id,
        "runKey": run.run_key,
        "channel": run.channel,
        "conversationId": run.conversation_id,
        "senderId": run.sender_id,
        "status": run.status,
        "intent": run.intent,
        "route": run.route,
        "toolName": run.tool_name,
        "input": run.input_text,
        "output": run.output_text,
        "error": run.error,
        "state": run.state_json or {},
        "createdAt": run.created_at.isoformat() if run.created_at else "",
        "updatedAt": run.updated_at.isoformat() if run.updated_at else "",
        "steps": [agent_step_payload(item) for item in steps or []],
        "toolCalls": [tool_call_payload(item) for item in tool_calls or []],
    }


def agent_step_payload(step: AgentStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "name": step.name,
        "status": step.status,
        "detail": step.detail_json or {},
        "createdAt": step.created_at.isoformat() if step.created_at else "",
    }


def tool_call_payload(call: AgentToolCall) -> dict[str, Any]:
    return {
        "id": call.id,
        "toolName": call.tool_name,
        "status": call.status,
        "input": call.input_json or {},
        "output": call.output_json or {},
        "error": call.error,
        "createdAt": call.created_at.isoformat() if call.created_at else "",
    }


def safe_json(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return {"value": str(value)}
