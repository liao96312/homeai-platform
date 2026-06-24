"""Lightweight conversation memory on top of ChromaDB."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

from backend.app.core.chroma import get_chroma_client
from backend.app.services.embeddings import embed_text
from backend.app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "conversation_memory"
MEMORY_CIRCUIT_FAILURE_THRESHOLD = 3
MEMORY_CIRCUIT_COOLDOWN_SECONDS = 60

_memory_failures: Counter[str] = Counter()
_memory_last_error: dict[str, str] = {}
_memory_circuit_open_until: dict[str, float] = {}


def _memory_circuit_open(operation: str | None = None) -> bool:
    now = time.monotonic()
    if operation:
        return now < _memory_circuit_open_until.get(operation, 0.0)
    return any(now < until for until in _memory_circuit_open_until.values())


def _record_memory_failure(operation: str, exc: Exception) -> None:
    _memory_failures[operation] += 1
    _memory_last_error[operation] = type(exc).__name__
    if _memory_failures[operation] >= MEMORY_CIRCUIT_FAILURE_THRESHOLD:
        _memory_circuit_open_until[operation] = time.monotonic() + MEMORY_CIRCUIT_COOLDOWN_SECONDS


def memory_health() -> dict:
    now = time.monotonic()
    retry_after = {operation: max(0, int(until - now)) for operation, until in _memory_circuit_open_until.items() if now < until}
    return {
        "ok": not bool(_memory_failures) and not _memory_circuit_open(),
        "circuitOpen": _memory_circuit_open(),
        "retryAfterSeconds": max(retry_after.values(), default=0),
        "operationRetryAfterSeconds": retry_after,
        "failures": dict(_memory_failures),
        "lastErrors": dict(_memory_last_error),
    }


def _get_memory_collection():
    if _memory_circuit_open("open_collection"):
        return None
    try:
        return get_chroma_client().get_or_create_collection(
            name=MEMORY_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as exc:
        _record_memory_failure("open_collection", exc)
        logger.warning("Failed to open memory collection", exc_info=True)
        return None


def remember(user_id: str, content: str, metadata: dict | None = None) -> str:
    """Store a memory fact for a user. Returns the memory id."""
    if _memory_circuit_open("remember"):
        return ""
    mem_id = f"mem_{user_id}_{uuid.uuid4().hex[:12]}"
    try:
        embedding = embed_text(content)
        coll = _get_memory_collection()
        if coll is None:
            return ""
        meta = {"user_id": user_id, "timestamp": datetime.now(timezone.utc).isoformat(), **(metadata or {})}
        coll.add(
            ids=[mem_id],
            documents=[content],
            embeddings=[embedding],
            metadatas=[meta],
        )
    except Exception as exc:
        _record_memory_failure("remember", exc)
        logger.warning("Failed to store memory for user=%s", user_id, exc_info=True)
        return ""
    return mem_id


def recall(user_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Retrieve relevant memories for a user given a query."""
    if _memory_circuit_open("recall"):
        return []
    try:
        coll = _get_memory_collection()
        if coll is None:
            return []
        query_embedding = embed_text(query)
        results = coll.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"user_id": user_id},
            include=["documents", "metadatas", "distances"],
        )
        memories = []
        if results["ids"] and results["ids"][0]:
            for i, mid in enumerate(results["ids"][0]):
                doc = (results["documents"][0] or [""])[i] if results["documents"] else ""
                dist = (results["distances"][0] or [0])[i] if results["distances"] else 0
                meta = (results["metadatas"][0] or [{}])[i] if results["metadatas"] else {}
                memories.append({
                    "id": mid,
                    "content": doc,
                    "score": round(1.0 - dist, 4),
                    "timestamp": meta.get("timestamp", ""),
                })
        return memories
    except Exception as exc:
        _record_memory_failure("recall", exc)
        logger.warning("Failed to recall memories for user=%s", user_id, exc_info=True)
        return []


def build_memory_context(memories: list[dict]) -> str:
    """Format recalled memories into a context string for the LLM prompt."""
    if not memories:
        return ""
    parts = ["以下是用户的历史对话摘要（长期记忆）：", ""]
    for i, memory in enumerate(memories, 1):
        parts.append(f"{i}. {memory['content']}")
    return "\n".join(parts)


def summarize_and_remember(user_id: str, user_message: str, assistant_reply: str) -> None:
    """Extract key facts from a conversation turn and store as memory."""
    if _memory_circuit_open("summarize_with_llm"):
        return
    provider = get_llm_provider()
    facts = summarize_with_llm(user_message, assistant_reply) if provider.available() else []
    if not facts:
        facts = summarize_with_heuristics(user_message, assistant_reply)
    for fact in facts[:5]:
        remember(user_id, fact, {"source": "conversation_summary"})


def summarize_with_llm(user_message: str, assistant_reply: str) -> list[str]:
    prompt = (
        "请从以下一轮对话中提取适合长期记忆的稳定事实、客户偏好、项目约束或明确待办。"
        "不要保存寒暄、临时闲聊、无意义复述。返回 JSON 数组，每项不超过 60 个中文字符；如果没有值得记忆的信息，返回 []。\n\n"
        f"用户：{user_message[:1200]}\n"
        f"助手：{assistant_reply[:1200]}"
    )
    try:
        provider = get_llm_provider()
        if not provider.available():
            return []
        response = provider.chat_completion(
            {
                "model": provider.default_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 300,
            },
            timeout=20,
        )
        content = response["choices"][0]["message"]["content"]
        match = re.search(r"\[[\s\S]*\]", content)
        data = json.loads(match.group(0) if match else content)
        return [str(item).strip() for item in data if isinstance(item, str) and is_memory_worthy(item)]
    except Exception as exc:
        _record_memory_failure("summarize_with_llm", exc)
        logger.warning("LLM memory summarization failed; falling back to heuristic", exc_info=True)
        return []


def summarize_with_heuristics(user_message: str, assistant_reply: str) -> list[str]:
    text = "\n".join([user_message, assistant_reply])
    sentences = re.split(r"[。！？\n]", text)
    facts = []
    useful_terms = (
        "客户", "预算", "面积", "户型", "风格", "喜欢", "偏好", "关注",
        "需求", "计划", "时间", "电话", "城市", "材料",
    )
    for sentence in sentences:
        cleaned = sentence.strip()
        if len(cleaned) < 12 or len(cleaned) > 120:
            continue
        if not any(term in cleaned for term in useful_terms):
            continue
        if is_memory_worthy(cleaned) and cleaned not in facts:
            facts.append(cleaned)
    return facts[:3]


def is_memory_worthy(text: str) -> bool:
    noisy = ("你好", "在吗", "谢谢", "可以", "好的", "暂无", "无法", "我是")
    return bool(text.strip()) and not any(term in text for term in noisy)
