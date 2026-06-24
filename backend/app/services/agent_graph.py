from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import commit_or_rollback
from backend.app.models.domain import AgentRun, User
from backend.app.services.agent_catalog import AGENT_TOOL_CATALOG
from backend.app.services.agent_intent import classify_agent_intent
from backend.app.services.agent_store import add_agent_step, add_tool_call, reset_failed_transaction, safe_json
from backend.app.services.agent_types import AgentExecutor, AgentReplyFormatter, RuntimeState

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
    LANGGRAPH_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on optional runtime import
    END = START = StateGraph = None  # type: ignore[assignment]
    LANGGRAPH_AVAILABLE = False
    LANGGRAPH_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


def execute_runtime_graph(
    *,
    db: Session,
    run: AgentRun,
    user: User,
    text: str,
    channel: str,
    executor: AgentExecutor,
    reply_formatter: AgentReplyFormatter,
    max_attempts: int = 1,
) -> RuntimeState:
    initial: RuntimeState = {"text": text, "channel": channel, "run_id": run.id, "max_attempts": max_attempts}

    def classify_node(state: RuntimeState) -> RuntimeState:
        plan = classify_agent_intent(state["text"])
        plan["toolSpec"] = next((item for item in AGENT_TOOL_CATALOG if item["name"] == plan.get("tool")), None)
        run.intent = plan["intent"]
        run.route = plan["route"]
        run.tool_name = plan["tool"]
        run.state_json = {**(run.state_json or {}), "plan": plan}
        add_agent_step(db, run, "intent_classification", detail=plan)
        return {"plan": plan}

    def make_tool_node(node_name: str, expected_route: str) -> Callable[[RuntimeState], RuntimeState]:
        def tool_node(state: RuntimeState) -> RuntimeState:
            plan = state.get("plan") or {}
            attempts = max(1, int(state.get("max_attempts") or 1))
            step = add_agent_step(
                db,
                run,
                node_name,
                "running",
                {
                    "tool": plan.get("tool"),
                    "route": plan.get("route"),
                    "expectedRoute": expected_route,
                    "maxAttempts": attempts,
                },
            )
            last_error = ""
            for attempt in range(1, attempts + 1):
                try:
                    result = executor(state["text"], user, db, str(run.id))
                    add_tool_call(
                        db,
                        run,
                        tool_name=result.get("tool") or plan.get("tool") or "",
                        input_data={
                            "text": state["text"],
                            "route": plan.get("route"),
                            "expectedRoute": expected_route,
                            "channel": state["channel"],
                            "attempt": attempt,
                        },
                        output_data=safe_json(result),
                    )
                    step.status = "completed"
                    step.detail_json = {**(step.detail_json or {}), "completed": True, "attempts": attempt}
                    commit_or_rollback(db)
                    return {"result": result}
                except Exception as exc:
                    reset_failed_transaction(db)
                    last_error = str(getattr(exc, "detail", None) or str(exc) or type(exc).__name__)
                    add_tool_call(
                        db,
                        run,
                        tool_name=str(plan.get("tool") or ""),
                        input_data={
                            "text": state["text"],
                            "route": plan.get("route"),
                            "expectedRoute": expected_route,
                            "channel": state["channel"],
                            "attempt": attempt,
                        },
                        output_data={},
                        status_text="failed",
                        error=last_error[:2000],
                    )
                    if attempt >= attempts:
                        step.status = "failed"
                        step.detail_json = {**(step.detail_json or {}), "attempts": attempt, "error": last_error[:2000]}
                        commit_or_rollback(db)
                        raise
            raise RuntimeError(last_error or "tool_execution_failed")

        return tool_node

    def human_review_gate_node(state: RuntimeState) -> RuntimeState:
        plan = state.get("plan") or {}
        result = dict(state.get("result") or {})
        result["requiresHumanReview"] = True
        result["reviewReason"] = "tool_policy_requires_review"
        add_agent_step(
            db,
            run,
            "human_review_gate",
            "pending_review",
            {
                "tool": plan.get("tool"),
                "route": plan.get("route"),
                "reason": "tool_policy_requires_review",
            },
        )
        return {"result": result, "requires_human_review": True}

    def route_from_plan(state: RuntimeState) -> str:
        route = (state.get("plan") or {}).get("route") or "chat"
        if route in {"sales", "design", "promo", "video"}:
            return f"{route}_agent"
        return "chat_agent"

    def review_or_answer(state: RuntimeState) -> str:
        plan = state.get("plan") or {}
        tool_spec = plan.get("toolSpec") or {}
        return "human_review_gate" if tool_spec.get("requiresHumanReview") else "answer_generation"

    def answer_node(state: RuntimeState) -> RuntimeState:
        reply = reply_formatter(state.get("result") or {})
        return {"reply": reply}

    graph = None
    runtime_name = "fallback"
    runtime_fallback_reason = LANGGRAPH_IMPORT_ERROR or ""
    if settings.agent_runtime_required and not LANGGRAPH_AVAILABLE:
        raise RuntimeError(f"LangGraph runtime is required but unavailable: {LANGGRAPH_IMPORT_ERROR}")
    if LANGGRAPH_AVAILABLE and StateGraph is not None and START is not None and END is not None:
        builder = StateGraph(RuntimeState)
        builder.add_node("intent_classification", classify_node)
        builder.add_node("sales_agent", make_tool_node("sales_agent_execution", "sales"))
        builder.add_node("design_agent", make_tool_node("design_agent_execution", "design"))
        builder.add_node("promo_agent", make_tool_node("promo_agent_execution", "promo"))
        builder.add_node("video_agent", make_tool_node("video_agent_execution", "video"))
        builder.add_node("chat_agent", make_tool_node("chat_agent_execution", "chat"))
        builder.add_node("human_review_gate", human_review_gate_node)
        builder.add_node("answer_generation", answer_node)
        builder.add_edge(START, "intent_classification")
        builder.add_conditional_edges(
            "intent_classification",
            route_from_plan,
            {
                "sales_agent": "sales_agent",
                "design_agent": "design_agent",
                "promo_agent": "promo_agent",
                "video_agent": "video_agent",
                "chat_agent": "chat_agent",
            },
        )
        for node_name in ("sales_agent", "design_agent", "promo_agent", "video_agent", "chat_agent"):
            builder.add_conditional_edges(
                node_name,
                review_or_answer,
                {
                    "human_review_gate": "human_review_gate",
                    "answer_generation": "answer_generation",
                },
            )
        builder.add_edge("human_review_gate", "answer_generation")
        builder.add_edge("answer_generation", END)
        graph = builder.compile()
        runtime_name = "langgraph"
        runtime_fallback_reason = ""
    else:
        logger.warning("LangGraph unavailable; using linear agent execution: %s", LANGGRAPH_IMPORT_ERROR)
        graph = None

    run.state_json = {
        **(run.state_json or {}),
        "runtime": runtime_name,
        "runtimeFallbackReason": runtime_fallback_reason,
    }
    commit_or_rollback(db)
    if graph is not None:
        return graph.invoke(initial)
    state = {**initial, **classify_node(initial)}
    fallback_route = ((state.get("plan") or {}).get("route") or "chat").strip() or "chat"
    state = {**state, **make_tool_node(f"{fallback_route}_agent_execution", fallback_route)(state)}
    if review_or_answer(state) == "human_review_gate":
        state = {**state, **human_review_gate_node(state)}
    return {**state, **answer_node(state)}
