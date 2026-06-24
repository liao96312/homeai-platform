from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.session import commit_or_rollback
from backend.app.models.domain import User
from backend.app.services.agent_catalog import AGENT_TOOL_CATALOG
from backend.app.services.agent_graph import LANGGRAPH_AVAILABLE, LANGGRAPH_IMPORT_ERROR, execute_runtime_graph
from backend.app.services.agent_intent import classify_agent_intent
from backend.app.services.agent_store import (
    agent_run_payload,
    cancel_agent_run,
    create_agent_run,
    get_agent_run_or_404,
    list_agent_steps,
    list_tool_calls,
    mark_agent_run_failed,
    mark_stale_running_runs_failed,
    request_handoff,
    reset_failed_transaction,
    resume_handoff,
    safe_json,
)
from backend.app.services.agent_types import AgentExecutor, AgentReplyFormatter


def run_agent(
    db: Session,
    *,
    user: User,
    text: str,
    executor: AgentExecutor,
    reply_formatter: AgentReplyFormatter,
    channel: str = "web",
    conversation_id: str = "",
    sender_id: str = "",
    metadata: dict[str, Any] | None = None,
    max_attempts: int = 1,
) -> dict[str, Any]:
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent 输入不能为空")
    run = create_agent_run(
        db,
        user=user,
        text=text,
        channel=channel,
        conversation_id=conversation_id,
        sender_id=sender_id,
        metadata=metadata,
    )
    try:
        state = execute_runtime_graph(
            db=db,
            run=run,
            user=user,
            text=text,
            channel=channel,
            executor=executor,
            reply_formatter=reply_formatter,
            max_attempts=max(1, min(max_attempts, 3)),
        )
        result = state.get("result") or {}
        reply = state.get("reply") or ""
        run.status = "completed"
        run.route = result.get("route") or run.route
        run.tool_name = result.get("tool") or run.tool_name
        if run.route and run.route != "chat":
            run.conversation_id = run.route
        run.output_text = reply
        run.updated_at = datetime.now(timezone.utc)
        run.state_json = {**(run.state_json or {}), "result": safe_json(result)}
        commit_or_rollback(db)
        from backend.app.services.agent_store import add_agent_step

        add_agent_step(db, run, "answer_generation", detail={"replyPreview": reply[:300]})
        db.refresh(run)
        return agent_run_payload(run, steps=list_agent_steps(db, run.id), tool_calls=list_tool_calls(db, run.id))
    except HTTPException as exc:
        reset_failed_transaction(db)
        mark_agent_run_failed(db, run, str(exc.detail))
        raise
    except Exception as exc:
        reset_failed_transaction(db)
        mark_agent_run_failed(db, run, type(exc).__name__)
        raise


__all__ = [
    "AGENT_TOOL_CATALOG",
    "LANGGRAPH_AVAILABLE",
    "LANGGRAPH_IMPORT_ERROR",
    "agent_run_payload",
    "cancel_agent_run",
    "classify_agent_intent",
    "get_agent_run_or_404",
    "list_agent_steps",
    "list_tool_calls",
    "mark_stale_running_runs_failed",
    "request_handoff",
    "resume_handoff",
    "run_agent",
]
