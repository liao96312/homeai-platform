import json
import logging
import re
from typing import Any

from backend.app.core.config import settings
from backend.app.services.embeddings import tokenize
from backend.app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)
RERANK_HIT_THRESHOLD = 0.55
RERANK_MAYBE_THRESHOLD = 0.34


def evaluate_retrieval(chunks: list[dict[str, Any]], gate: dict[str, Any] | None = None) -> dict[str, Any]:
    if gate and not gate.get("allowed"):
        return {
            "passed": False,
            "level": "miss",
            "topRerankScore": 0,
            "thresholds": {"hit": RERANK_HIT_THRESHOLD, "maybe": RERANK_MAYBE_THRESHOLD},
            "reason": "intent_gate_blocked",
        }
    if not chunks:
        return {
            "passed": False,
            "level": "miss",
            "topRerankScore": 0,
            "thresholds": {"hit": RERANK_HIT_THRESHOLD, "maybe": RERANK_MAYBE_THRESHOLD},
            "reason": "no_retrieved_chunks",
        }

    top_rerank = max(float(chunk.get("rerankScore") or 0) for chunk in chunks)
    high_relevance = any((chunk.get("relevance") or {}).get("level") == "high" for chunk in chunks)
    if top_rerank >= RERANK_HIT_THRESHOLD and high_relevance:
        level = "hit"
        passed = True
        reason = "reranker_high_confidence"
    elif top_rerank >= RERANK_MAYBE_THRESHOLD:
        level = "maybe"
        passed = True
        reason = "reranker_marginal"
    else:
        level = "miss"
        passed = False
        reason = "reranker_below_threshold"
    return {
        "passed": passed,
        "level": level,
        "topRerankScore": round(top_rerank, 4),
        "thresholds": {"hit": RERANK_HIT_THRESHOLD, "maybe": RERANK_MAYBE_THRESHOLD},
        "reason": reason,
    }


def evaluate_rag_triad(
    query: str,
    answer: str,
    chunks: list[dict[str, Any]],
    gate: dict[str, Any] | None,
    retrieval: dict[str, Any],
) -> dict[str, Any]:
    if gate and not gate.get("allowed"):
        return {
            "passed": False,
            "groundedness": 0,
            "answerRelevance": 0,
            "contextRelevance": 0,
            "reason": "intent_gate_blocked_before_rag",
        }
    if not chunks:
        return {
            "passed": False,
            "groundedness": 0,
            "answerRelevance": 0,
            "contextRelevance": 0,
            "reason": "no_context_for_triad",
        }
    if settings.rag_triad_llm_judge_enabled:
        llm_result = evaluate_rag_triad_with_llm(query, answer, chunks)
        if llm_result:
            return llm_result

    context = "\n".join(str(chunk.get("content") or "") for chunk in chunks)
    groundedness = token_overlap_ratio(answer, context)
    answer_relevance = token_overlap_ratio(query, answer)
    context_relevance = min(1.0, float(retrieval.get("topRerankScore") or 0))
    tail_groundedness = answer_tail_overlap_ratio(answer, context)

    passed = groundedness >= 0.25 and tail_groundedness >= 0.18 and answer_relevance >= 0.12 and context_relevance >= RERANK_HIT_THRESHOLD
    if passed:
        reason = "answer_grounded_and_relevant"
    elif context_relevance >= RERANK_MAYBE_THRESHOLD:
        reason = "triad_needs_human_confirmation"
    else:
        reason = "triad_failed"
    return {
        "passed": passed,
        "groundedness": round(groundedness, 4),
        "tailGroundedness": round(tail_groundedness, 4),
        "answerRelevance": round(answer_relevance, 4),
        "contextRelevance": round(context_relevance, 4),
        "thresholds": {
            "groundedness": 0.25,
            "tailGroundedness": 0.18,
            "answerRelevance": 0.12,
            "contextRelevance": RERANK_HIT_THRESHOLD,
        },
        "reason": reason,
        "method": "local_overlap",
    }


def evaluate_rag_triad_with_llm(query: str, answer: str, chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not settings.rag_triad_llm_judge_enabled:
        return None
    provider = get_llm_provider()
    if not provider.available() or not query.strip() or not answer.strip():
        return None
    context = "\n\n".join(str(chunk.get("content") or "")[:1200] for chunk in chunks[:4])
    prompt = (
        "你是 RAG 质量评估器。请基于问题、资料和回答，输出 JSON："
        '{"groundedness":0到1,"answerRelevance":0到1,"contextRelevance":0到1,"reason":"简短原因"}。'
        "groundedness 表示回答是否被资料支撑；answerRelevance 表示是否切题；contextRelevance 表示资料是否相关。只输出 JSON。\n\n"
        f"问题：{query[:1200]}\n\n资料：{context}\n\n回答：{answer[:1600]}"
    )
    try:
        resp = provider.chat_completion(
            {
                "model": settings.deepseek_default_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 250,
                "response_format": {"type": "json_object"},
            },
            timeout=min(settings.ai_request_timeout_seconds, 20),
        )
        raw = resp["choices"][0]["message"]["content"]
        data = json.loads(raw)
        groundedness = clamp_score(data.get("groundedness"))
        answer_relevance = clamp_score(data.get("answerRelevance"))
        context_relevance = clamp_score(data.get("contextRelevance"))
        passed = groundedness >= 0.7 and answer_relevance >= 0.7 and context_relevance >= 0.7
        return {
            "passed": passed,
            "groundedness": groundedness,
            "answerRelevance": answer_relevance,
            "contextRelevance": context_relevance,
            "thresholds": {"groundedness": 0.7, "answerRelevance": 0.7, "contextRelevance": 0.7},
            "reason": str(data.get("reason") or ("llm_judge_passed" if passed else "llm_judge_failed")),
            "method": "llm_judge",
        }
    except Exception:
        logger.warning("LLM RAG triad judge failed; using local fallback", exc_info=True)
        return None


def clamp_score(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def token_overlap_ratio(left: str, right: str) -> float:
    left_terms = meaningful_terms(left)
    right_terms = meaningful_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(1, len(left_terms))


def answer_tail_overlap_ratio(answer: str, context: str) -> float:
    answer = answer or ""
    if not answer.strip():
        return 0.0
    start = max(0, int(len(answer) * 0.7))
    return token_overlap_ratio(answer[start:], context)


def meaningful_terms(text: str) -> set[str]:
    terms = set(tokenize(text or ""))
    return {term for term in terms if is_meaningful_term(term)}


def is_meaningful_term(term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_]{2,}", term):
        return True
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", term))

