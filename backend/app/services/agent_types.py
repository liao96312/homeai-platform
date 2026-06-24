from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from backend.app.models.domain import User

AgentExecutor = Callable[[str, User, Session, str | None], dict[str, Any]]
AgentReplyFormatter = Callable[[dict[str, Any]], str]


class RuntimeState(TypedDict, total=False):
    text: str
    channel: str
    run_id: int
    max_attempts: int
    plan: dict[str, Any]
    result: dict[str, Any]
    reply: str
    requires_human_review: bool
