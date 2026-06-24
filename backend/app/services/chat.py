import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.core.config import settings
from backend.app.db.session import commit_or_rollback
from backend.app.models.domain import RagQueryLog
from backend.app.services.chat_payloads import build_deepseek_payload, extract_text, merge_system_message
from backend.app.services.llm import get_llm_provider
from backend.app.services.rag import build_rag_prompt, retrieve_context, save_conversation_turn
from backend.app.services.rag_gate import classify_rag_query, rag_gate_observation
from backend.app.services.rag_quality import (
    RERANK_HIT_THRESHOLD,
    RERANK_MAYBE_THRESHOLD,
    evaluate_rag_triad,
    evaluate_rag_triad_with_llm,
    evaluate_retrieval,
)
from backend.app.services.runtime_metrics import record_runtime_failure

logger = logging.getLogger(__name__)
__all__ = ["evaluate_rag_triad_with_llm"]

RAG_STATUS_HIT = {"code": "hit", "label": "✅ 已命中知识库"}
RAG_STATUS_MAYBE = {"code": "maybe", "label": "⚠ 可能相关，建议人工确认"}
RAG_STATUS_MISS = {"code": "miss", "label": "❌ 知识库未命中"}

RAG_MISS_REFUSAL = (
    "抱歉，知识库中暂无相关信息可以回答您的问题。\n\n"
    "建议您：\n"
    "1. 换个方式描述您的问题\n"
    "2. 联系管理员补充相关知识库资料\n"
    "3. 直接咨询人工顾问获取帮助"
)

RAG_NON_BUSINESS_REFUSAL = (
    "抱歉，我目前专注于家装定制领域的专业问题解答。\n"
    "请提出与产品、设计、报价、工艺等相关的问题，我会基于知识库为您提供准确回答。"
)

SMALLTALK_INTENTS = {"greeting_identity", "emotional_chat", "weather_time", "food_drink", "personal_life"}
SMALLTALK_REASONS = {"non_business_smalltalk"}


class ChatMessage(BaseModel):
    role: str
    content: Any = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    prefix: bool | None = None
    reasoning_content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "deepseek-chat"
    messages: list[ChatMessage] = Field(min_length=1)
    provider: str | None = None
    temperature: float | None = 0.7
    top_p: float | None = 1.0
    n: int | None = 1
    stream: bool | None = False
    stop: str | list[str] | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    user: str | None = None
    metadata: dict[str, Any] | None = None
    thinking: dict[str, Any] | None = None



SAFETY_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"银行卡.{0,8}(密码|验证码|cvv|安全码)",
        r"(身份证|护照|社保卡).{0,8}(照片|扫描|正反面|号码)",
        r"(绕过|规避|突破).{0,8}(审核|风控|限制|检测)",
        r"(诈骗|洗钱|盗号|木马|钓鱼|非法|违法)",
        r"(爆破|撞库|拖库|脱库|社工库)",
        r"(代开发票|虚开发票|套现)",
        r"(自杀|自残|伤害自己|杀人|投毒)",
    ]
]


def safety_violation(text: str) -> str | None:
    for pattern in SAFETY_PATTERNS:
        if pattern.search(text or ""):
            return pattern.pattern
    return None


def assert_user_input_safe(req: ChatCompletionRequest) -> None:
    user_text = "\n".join(extract_text(message.content) for message in req.messages if message.role == "user")
    violation = safety_violation(user_text)
    if violation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户输入触发安全审核，请调整问题或联系管理员复核。",
        )


def apply_safety_review(result: dict[str, Any]) -> dict[str, Any]:
    choices = result.get("choices") or []
    if not choices:
        return result
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "")
    if not content:
        return result
    result.setdefault("metadata", {})
    if safety_violation(content):
        message["content"] = "这条回复触发了 AI 安全审核，已停止展示。请调整问题或联系管理员复核。"
        choices[0]["finish_reason"] = "content_filter"
        result["metadata"]["safety_review"] = "blocked"
    else:
        result["metadata"]["safety_review"] = "passed"
    return result


def evaluate_rag_gate(
    rag_gate: dict[str, Any] | None,
    rag_chunks: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Decide whether to block the LLM call due to RAG miss.

    Returns (should_block, refusal_message).
    """
    if rag_gate is None:
        return False, ""

    allowed = rag_gate.get("allowed", False)
    intent = rag_gate.get("intent", "")
    reason = rag_gate.get("reason", "")

    # Smalltalk / casual — let through without RAG
    if not allowed:
        if reason in SMALLTALK_REASONS or intent in SMALLTALK_INTENTS:
            return False, ""
        # Non-business query that isn't smalltalk — refuse politely
        return True, RAG_NON_BUSINESS_REFUSAL

    # Business domain query — check retrieval quality
    if not rag_chunks:
        return True, RAG_MISS_REFUSAL

    # Has chunks — only allow confirmed "hit", block "maybe" to prevent hallucination
    retrieval = evaluate_retrieval(rag_chunks, rag_gate)
    if retrieval.get("level") != "hit":
        return True, RAG_MISS_REFUSAL

    return False, ""


def build_refusal_response(
    refusal_msg: str,
    rag_gate: dict[str, Any] | None,
    rag_chunks: list[dict[str, Any]],
    query: str,
    user_id: str,
    db: Session | None,
    conversation_key: str | None,
    save_memory: bool,
) -> dict[str, Any]:
    """Build a refusal response that looks like a normal LLM response."""
    retrieval = evaluate_retrieval(rag_chunks, rag_gate) if rag_chunks else {
        "passed": False, "level": "miss", "topRerankScore": 0,
        "thresholds": {"hit": RERANK_HIT_THRESHOLD, "maybe": RERANK_MAYBE_THRESHOLD},
        "reason": "no_retrieved_chunks",
    }
    triads = {
        "passed": False, "groundedness": 0, "answerRelevance": 0, "contextRelevance": 0,
        "reason": "rag_gate_blocked",
    }
    status = {**RAG_STATUS_MISS, "reason": retrieval.get("reason", "rag_gate_blocked")}

    try:
        save_rag_query_log(db, user_id, conversation_key, query, rag_chunks, bool(rag_chunks), status, rag_gate=rag_gate)
    except Exception:
        logger.warning("Failed to save RAG query log", exc_info=True)

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": settings.deepseek_default_model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": refusal_msg},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "metadata": {
            "provider": "rag_gate",
            "mode": "refused",
            "rag": {
                "injected": bool(rag_chunks),
                "count": len(rag_chunks),
                "gate": rag_gate,
                "retrievals": retrieval,
                "triads": triads,
                "status": status,
                "citations": [],
            },
        },
    }


def create_chat_completion(
    req: ChatCompletionRequest,
    role_key: str,
    conversation_key: str | None = None,
    db: Session | None = None,
    user_id: str = "",
    save_memory: bool = True,
    safety_review: bool = True,
) -> dict[str, Any]:
    return create_deepseek_chat_completion(
        req,
        conversation_key=conversation_key,
        db=db,
        user_id=user_id,
        save_memory=save_memory,
        safety_review=safety_review,
    )


def should_use_deepseek(req: ChatCompletionRequest) -> bool:
    provider = (req.provider or settings.ai_provider or "deepseek").lower()
    return provider in {"deepseek", "openai-compatible", "openai_compatible"}


def llm_error_message(provider_name: str, exc: Exception) -> tuple[int, str]:
    if isinstance(exc, httpx.TimeoutException):
        return status.HTTP_504_GATEWAY_TIMEOUT, f"{provider_name} API 请求超时，请稍后重试或检查网络"
    if isinstance(exc, httpx.ConnectError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, f"无法连接 {provider_name} API，请检查 DEEPSEEK_BASE_URL 和服务器网络"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in {401, 403}:
            return status.HTTP_502_BAD_GATEWAY, f"{provider_name} API 鉴权失败，请检查 API Key 是否正确"
        if code == 429:
            return status.HTTP_429_TOO_MANY_REQUESTS, f"{provider_name} API 频率或额度受限，请稍后再试"
        if code >= 500:
            return status.HTTP_502_BAD_GATEWAY, f"{provider_name} API 服务暂时异常：HTTP {code}"
        return status.HTTP_502_BAD_GATEWAY, f"{provider_name} API 返回错误：HTTP {code}"
    return status.HTTP_502_BAD_GATEWAY, f"{provider_name} API 调用失败：{type(exc).__name__}"


def create_deepseek_chat_completion(
    req: ChatCompletionRequest,
    conversation_key: str | None = None,
    db: Session | None = None,
    user_id: str = "",
    save_memory: bool = True,
    safety_review: bool = True,
    invoke: Any | None = None,
) -> dict[str, Any]:
    context = _prepare_chat_completion(req, conversation_key, db, user_id, safety_review, save_memory)
    if isinstance(context, dict):
        return context  # RAG gate refusal or other early dict response

    payload = context["payload"]
    provider = context["provider"]
    rag_chunks = context["rag_chunks"]
    rag_context_str = context["rag_context_str"]
    rag_gate = context["rag_gate"]
    last_user_text = context["last_user_text"]

    try:
        data = (invoke or provider.chat_completion)(payload)
    except Exception as exc:
        logger.warning("%s API call failed", provider.name, exc_info=True)
        status_code, detail = llm_error_message(provider.name, exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc

    return _finalize_chat_completion(
        data, provider, rag_chunks, rag_context_str, rag_gate, last_user_text,
        db, user_id, conversation_key, save_memory, safety_review,
    )


async def create_deepseek_chat_completion_async(
    req: ChatCompletionRequest,
    conversation_key: str | None = None,
    db: Session | None = None,
    user_id: str = "",
    save_memory: bool = True,
    safety_review: bool = True,
) -> dict[str, Any]:
    """Async variant for use inside async routes — awaits the upstream LLM call
    instead of blocking the event loop. Shares all RAG/safety/persistence logic
    with the sync version."""
    context = await _prepare_chat_completion_async(req, conversation_key, db, user_id, safety_review, save_memory)
    if isinstance(context, dict):
        return context  # RAG gate refusal or other early dict response

    payload = context["payload"]
    provider = context["provider"]

    try:
        data = await provider.chat_completion_async(payload)
    except Exception as exc:
        logger.warning("%s API call failed", provider.name, exc_info=True)
        status_code, detail = llm_error_message(provider.name, exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc

    return _finalize_chat_completion(
        data, provider, context["rag_chunks"], context["rag_context_str"],
        context["rag_gate"], context["last_user_text"],
        db, user_id, conversation_key, save_memory, safety_review,
    )


def _prepare_chat_completion(
    req: ChatCompletionRequest,
    conversation_key: str | None,
    db: Session | None,
    user_id: str,
    safety_review: bool,
    save_memory: bool = True,
) -> dict[str, Any]:
    """Build the LLM payload and resolve RAG context. Returns either an early
    response dict (RAG-gate refusal) or a context dict for the caller to send."""
    rag_chunks: list[dict[str, Any]] = []
    rag_context_str = ""
    rag_gate: dict[str, Any] | None = None
    last_user_text = ""
    if db and conversation_key:
        try:
            last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
            if last_user:
                last_user_text = extract_text(last_user.content)
                if last_user_text.strip():
                    rag_gate = classify_rag_query(last_user_text)
                    rag_chunks, rag_context_str = retrieve_context(db, last_user_text, conversation_key, user_id=user_id, gate=rag_gate)
                    if not rag_chunks:
                        rag_context_str = ""
        except Exception as exc:
            record_runtime_failure("rag_context_retrieval_failed", exc)
            logger.warning("RAG context retrieval failed, proceeding without context", exc_info=True)

    # —— RAG 闸门：知识库未命中时阻止 LLM 调用 ——
    if db and conversation_key:
        should_block, refusal_msg = evaluate_rag_gate(rag_gate, rag_chunks)
        if should_block:
            return build_refusal_response(refusal_msg, rag_gate, rag_chunks, last_user_text, user_id, db, conversation_key, save_memory)

    provider = get_llm_provider(req.provider)
    if not provider.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider.name} API Key 未配置，无法调用真实模型",
        )

    if safety_review:
        assert_user_input_safe(req)

    payload = build_deepseek_payload(req)
    if rag_context_str:
        merge_system_message(payload["messages"], build_rag_prompt(rag_context_str, conversation_key or "admin"))

    return {
        "payload": payload,
        "provider": provider,
        "rag_chunks": rag_chunks,
        "rag_context_str": rag_context_str,
        "rag_gate": rag_gate,
        "last_user_text": last_user_text,
    }


async def _prepare_chat_completion_async(
    req: ChatCompletionRequest,
    conversation_key: str | None,
    db: Session | None,
    user_id: str,
    safety_review: bool,
    save_memory: bool = True,
) -> dict[str, Any]:
    rag_chunks: list[dict[str, Any]] = []
    rag_context_str = ""
    rag_gate: dict[str, Any] | None = None
    last_user_text = ""
    if db and conversation_key:
        try:
            last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
            if last_user:
                last_user_text = extract_text(last_user.content)
                if last_user_text.strip():
                    rag_gate = classify_rag_query(last_user_text)
                    rag_chunks, rag_context_str = await run_in_threadpool(
                        retrieve_context,
                        db,
                        last_user_text,
                        conversation_key,
                        user_id,
                        5,
                        rag_gate,
                    )
                    if not rag_chunks:
                        rag_context_str = ""
        except Exception as exc:
            record_runtime_failure("rag_context_retrieval_failed", exc)
            logger.warning("RAG context retrieval failed, proceeding without context", exc_info=True)

    if db and conversation_key:
        should_block, refusal_msg = evaluate_rag_gate(rag_gate, rag_chunks)
        if should_block:
            return build_refusal_response(refusal_msg, rag_gate, rag_chunks, last_user_text, user_id, db, conversation_key, save_memory)

    provider = get_llm_provider(req.provider)
    if not provider.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider.name} API Key 未配置，无法调用真实模型",
        )

    if safety_review:
        assert_user_input_safe(req)

    payload = build_deepseek_payload(req)
    if rag_context_str:
        merge_system_message(payload["messages"], build_rag_prompt(rag_context_str, conversation_key or "admin"))

    return {
        "payload": payload,
        "provider": provider,
        "rag_chunks": rag_chunks,
        "rag_context_str": rag_context_str,
        "rag_gate": rag_gate,
        "last_user_text": last_user_text,
    }


def _finalize_chat_completion(
    data: dict[str, Any],
    provider: Any,
    rag_chunks: list[dict[str, Any]],
    rag_context_str: str,
    rag_gate: dict[str, Any] | None,
    last_user_text: str,
    db: Session | None,
    user_id: str,
    conversation_key: str | None,
    save_memory: bool,
    safety_review: bool,
) -> dict[str, Any]:
    assistant_reply = ""
    if data.get("choices"):
        assistant_reply = data["choices"][0].get("message", {}).get("content", "")

    data.setdefault("metadata", {})
    data["metadata"]["provider"] = provider.name
    data["metadata"]["mode"] = "upstream"
    data["metadata"]["rag"] = build_rag_metadata(rag_chunks, bool(rag_context_str), rag_gate, last_user_text, assistant_reply)
    try:
        save_rag_query_log(
            db,
            user_id,
            conversation_key,
            last_user_text,
            rag_chunks,
            bool(rag_context_str),
            data["metadata"]["rag"].get("status"),
            rag_gate=rag_gate,
        )
    except Exception:
        logger.warning("Failed to save RAG query log", exc_info=True)

    if save_memory and user_id and last_user_text and assistant_reply:
        try:
            save_conversation_turn(user_id, last_user_text, assistant_reply)
        except Exception as exc:
            record_runtime_failure("memory_save_failed", exc)
            logger.warning("Failed to save conversation memory", exc_info=True)

    return apply_safety_review(data) if safety_review else data


def build_rag_metadata(
    chunks: list[dict[str, Any]],
    injected: bool,
    gate: dict[str, Any] | None = None,
    query: str = "",
    answer: str = "",
) -> dict[str, Any]:
    retrieval = evaluate_retrieval(chunks, gate)
    triad = evaluate_rag_triad(query, answer, chunks, gate, retrieval)
    status = choose_rag_status(gate, retrieval, triad)
    return {
        "injected": injected,
        "count": len(chunks),
        "gate": gate,
        "retrieval": retrieval,
        "triad": triad,
        "status": status,
        "citations": [
            {
                "rank": chunk.get("rank", index + 1),
                "score": chunk.get("score"),
                "vectorScore": chunk.get("vectorScore"),
                "bm25Score": chunk.get("bm25Score"),
                "rerankScore": chunk.get("rerankScore"),
                "searchMode": chunk.get("searchMode"),
                "fusion": chunk.get("fusion"),
                "relevance": chunk.get("relevance"),
                "kbKey": chunk.get("kb_key"),
                "kbName": chunk.get("kb_name"),
                "documentId": chunk.get("documentId"),
                "chunkId": chunk.get("chunkId"),
                "filename": chunk.get("filename"),
                "chunkIndex": chunk.get("chunkIndex"),
                "preview": str(chunk.get("content", ""))[:180],
            }
            for index, chunk in enumerate(chunks)
        ],
    }


def save_rag_query_log(
    db: Session | None,
    user_id: str,
    conversation_key: str | None,
    query: str,
    chunks: list[dict[str, Any]],
    injected: bool,
    rag_status: dict[str, Any] | None = None,
    top_k: int = 5,
    rag_gate: dict[str, Any] | None = None,
) -> None:
    if not db or not query.strip():
        return
    numeric_user_id = int(user_id) if str(user_id).isdigit() else None
    gate_observation = rag_gate_observation(rag_gate)
    top_sources = [
        {
            "rank": chunk.get("rank", index + 1),
            "kbKey": chunk.get("kb_key"),
            "kbName": chunk.get("kb_name"),
            "filename": chunk.get("filename"),
            "chunkId": chunk.get("chunkId"),
            "score": chunk.get("score"),
            "vectorScore": chunk.get("vectorScore"),
            "bm25Score": chunk.get("bm25Score"),
            "rerankScore": chunk.get("rerankScore"),
            "searchMode": chunk.get("searchMode"),
            "fusion": chunk.get("fusion"),
            "relevance": chunk.get("relevance"),
            "ragStatus": rag_status,
            "ragGate": gate_observation,
        }
        for index, chunk in enumerate(chunks[:top_k])
    ]
    if not top_sources and rag_status:
        top_sources = [{"type": "status", "ragStatus": rag_status, "ragGate": gate_observation}]
    db.add(
        RagQueryLog(
            user_id=numeric_user_id,
            conversation_key=conversation_key or "",
            query=query[:2000],
            top_k=top_k,
            hit_count=len(chunks),
            injected=injected,
            top_sources=top_sources,
            created_at_label="刚刚",
        )
    )
    commit_or_rollback(db)



def choose_rag_status(
    gate: dict[str, Any] | None,
    retrieval: dict[str, Any],
    triad: dict[str, Any],
) -> dict[str, Any]:
    if gate and not gate.get("allowed"):
        return {**RAG_STATUS_MISS, "reason": gate.get("reason")}
    if retrieval.get("level") == "miss":
        return {**RAG_STATUS_MISS, "reason": retrieval.get("reason")}
    if retrieval.get("level") == "hit" and triad.get("passed"):
        return {**RAG_STATUS_HIT, "reason": triad.get("reason")}
    return {**RAG_STATUS_MAYBE, "reason": triad.get("reason") or retrieval.get("reason")}



async def create_deepseek_chat_completion_stream(
    req: ChatCompletionRequest,
    conversation_key: str | None = None,
    db: Session | None = None,
    user_id: str = "",
    save_memory: bool = True,
    safety_review: bool = True,
    on_complete: Any | None = None,
) -> AsyncGenerator[str, None]:
    rag_chunks: list[dict[str, Any]] = []
    rag_context_str = ""
    rag_gate: dict[str, Any] | None = None
    last_user_text = ""
    if db and conversation_key:
        try:
            last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
            if last_user:
                last_user_text = extract_text(last_user.content)
                if last_user_text.strip():
                    rag_gate = classify_rag_query(last_user_text)
                    rag_chunks, rag_context_str = await run_in_threadpool(
                        retrieve_context,
                        db,
                        last_user_text,
                        conversation_key,
                        user_id,
                        5,
                        rag_gate,
                    )
                    if not rag_chunks:
                        rag_context_str = ""
        except Exception as exc:
            record_runtime_failure("stream_rag_retrieval_failed", exc)
            logger.warning("RAG retrieval failed for stream", exc_info=True)

    # —— RAG 闸门（流式）：知识库未命中时阻止 LLM 调用 ——
    if db and conversation_key:
        should_block, refusal_msg = evaluate_rag_gate(rag_gate, rag_chunks)
        if should_block:
            # Log refusal and yield as error chunk
            retrieval = evaluate_retrieval(rag_chunks, rag_gate) if rag_chunks else {
                "passed": False, "level": "miss", "topRerankScore": 0,
                "thresholds": {"hit": RERANK_HIT_THRESHOLD, "maybe": RERANK_MAYBE_THRESHOLD},
                "reason": "no_retrieved_chunks",
            }
            status = {**RAG_STATUS_MISS, "reason": retrieval.get("reason", "rag_gate_blocked")}
            try:
                save_rag_query_log(
                    db,
                    user_id,
                    conversation_key,
                    last_user_text,
                    rag_chunks,
                    bool(rag_chunks),
                    status,
                    rag_gate=rag_gate,
                )
            except Exception:
                logger.warning("Failed to save streamed RAG query log for refusal", exc_info=True)
            yield _error_stream_chunk(req, refusal_msg)
            yield "data: [DONE]\n\n"
            return

    provider = get_llm_provider(req.provider)
    if not provider.available():
        yield _error_stream_chunk(req, f"{provider.name} API Key 未配置，无法调用真实模型")
        yield "data: [DONE]\n\n"
        return

    if safety_review:
        try:
            assert_user_input_safe(req)
        except HTTPException as exc:
            yield _error_stream_chunk(req, str(exc.detail))
            yield "data: [DONE]\n\n"
            return

    payload = build_deepseek_payload(req)
    payload["stream"] = True
    if rag_context_str:
        merge_system_message(payload["messages"], build_rag_prompt(rag_context_str, conversation_key or "admin"))

    assistant_reply = ""
    finalized = False

    def finalize_partial_stream() -> None:
        nonlocal finalized
        if finalized:
            return
        finalized = True
        rag_metadata = build_rag_metadata(rag_chunks, bool(rag_context_str), rag_gate, last_user_text, assistant_reply)
        if save_memory and user_id and last_user_text and assistant_reply:
            try:
                save_conversation_turn(user_id, last_user_text, assistant_reply)
            except Exception:
                logger.warning("Failed to save conversation memory from stream", exc_info=True)
        try:
            save_rag_query_log(
                db,
                user_id,
                conversation_key,
                last_user_text,
                rag_chunks,
                bool(rag_context_str),
                rag_metadata.get("status"),
                rag_gate=rag_gate,
            )
        except Exception:
            logger.warning("Failed to save streamed RAG query log", exc_info=True)
        if on_complete and last_user_text and assistant_reply:
            try:
                on_complete(last_user_text, assistant_reply)
            except Exception:
                logger.warning("Failed to run stream completion callback", exc_info=True)

    try:
        async for line in provider.stream_chat_completion(payload):
            if line.startswith("data: "):
                data_str = line[len("data: "):]
                if data_str != "[DONE]":
                    try:
                        chunk_data = json.loads(data_str)
                        delta = (chunk_data.get("choices", [{}])[0].get("delta") or {})
                        if "content" in delta:
                            assistant_reply += delta["content"]
                    except json.JSONDecodeError:
                        pass
                yield f"{line}\n\n"
    except Exception as exc:
        logger.warning("%s stream failed", provider.name, exc_info=True)
        finalize_partial_stream()
        _, detail = llm_error_message(provider.name, exc)
        yield _error_stream_chunk(req, detail)
        yield "data: [DONE]\n\n"
        return

    finalize_partial_stream()


def _error_stream_chunk(req: ChatCompletionRequest, message: str) -> str:
    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": req.model or settings.deepseek_default_model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": message},
                "finish_reason": "error",
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


