import math
import re
from collections import Counter

from backend.app.models.domain import KnowledgeChunk
from backend.app.services.embeddings import tokenize
from backend.app.services.rag_gate import (
    RELEVANCE_THRESHOLDS,
    classify_rag_query,
    effective_query_terms,
    has_business_exact_term,
    is_strong_exact_term,
    query_quality,
)


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_relevance_evidence(query: str, item: dict, gate: dict | None = None) -> dict:
    text = query.strip().lower()
    query_terms = effective_query_terms(text)
    content_terms = set(tokenize(str(item.get("content", "")).lower()))
    overlap_terms = query_terms & content_terms
    overlap = len(overlap_terms) / max(1, len(query_terms))
    domain_intent = bool((gate or classify_rag_query(query)).get("domainIntent"))
    query_quality_info = (gate or {}).get("quality") or query_quality(text)
    has_keyword_evidence = overlap >= RELEVANCE_THRESHOLDS["keyword_overlap"]
    bm25_score = float(item.get("bm25Score") or 0)
    has_bm25_evidence = bm25_score > 0
    has_strong_bm25_evidence = bm25_score >= RELEVANCE_THRESHOLDS["bm25_strong"]
    has_rerank_evidence = float(item.get("rerankScore") or 0) >= RELEVANCE_THRESHOLDS["rerank_overlap"]
    has_strong_vector_evidence = domain_intent and float(item.get("vectorScore") or 0) >= RELEVANCE_THRESHOLDS["domain_vector"]
    has_strong_exact_term = any(is_strong_exact_term(term) for term in overlap_terms)
    reasons = []
    if has_keyword_evidence:
        reasons.append("keyword_overlap")
    if has_bm25_evidence:
        reasons.append("bm25")
    if has_strong_bm25_evidence:
        reasons.append("bm25_strong")
    if has_rerank_evidence:
        reasons.append("rerank_overlap")
    if has_strong_vector_evidence:
        reasons.append("domain_vector")

    has_domain_anchor = domain_intent or has_strong_exact_term or has_business_exact_term(overlap_terms)
    independent_signal_count = len({reason.replace("_strong", "") for reason in reasons})
    short_focused_query = len(query_terms) <= 8
    strong_single_signal = short_focused_query and domain_intent and has_strong_exact_term and (has_strong_bm25_evidence or has_rerank_evidence)
    accepted = (independent_signal_count >= RELEVANCE_THRESHOLDS["min_signals"] and has_domain_anchor) or strong_single_signal
    if not accepted:
        level = "rejected"
    elif has_keyword_evidence and (has_bm25_evidence or has_rerank_evidence):
        level = "high"
    elif has_bm25_evidence or has_rerank_evidence or has_strong_vector_evidence:
        level = "medium"
    else:
        level = "low"

    return {
        "accepted": accepted,
        "level": level,
        "reasons": reasons,
        "keywordOverlap": round(float(overlap), 4),
        "matchedTerms": sorted(overlap_terms)[:8],
        "strongExactTerm": has_strong_exact_term,
        "independentSignalCount": independent_signal_count,
        "shortFocusedQuery": short_focused_query,
        "domainIntent": domain_intent,
        "queryQuality": query_quality_info,
        "thresholds": RELEVANCE_THRESHOLDS,
    }


def passes_relevance_gate(query: str, item: dict) -> bool:
    return build_relevance_evidence(query, item)["accepted"]


def bm25_rank(query: str, chunks: list[KnowledgeChunk]) -> list[tuple[int, float]]:
    query_terms = tokenize(query)
    if not query_terms or not chunks:
        return []

    docs = [tokenize(chunk.content) for chunk in chunks]
    avgdl = sum(len(doc) for doc in docs) / max(1, len(docs))
    doc_freq: Counter[str] = Counter()
    for doc in docs:
        doc_freq.update(set(doc))

    k1 = 1.5
    b = 0.75
    scores: list[tuple[int, float]] = []
    for chunk, doc in zip(chunks, docs):
        if not doc:
            continue
        tf = Counter(doc)
        score = 0.0
        dl = len(doc)
        for term in query_terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * dl / max(avgdl, 1))
            score += idf * (freq * (k1 + 1)) / denom
        if score > 0:
            scores.append((chunk.id, score))
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores


def rank_scores(scores: dict[int, float]) -> dict[int, int]:
    ranked = [
        (key, float(value or 0.0))
        for key, value in scores.items()
        if float(value or 0.0) > 0
    ]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return {key: index + 1 for index, (key, _score) in enumerate(ranked)}


def defensive_rrf_score(
    chunk_id: int,
    rankings: dict[str, dict[int, int]],
    *,
    vector_score: float,
    query_quality: dict,
    k: int = 60,
) -> float:
    vector_weight = 0.55
    bm25_weight = 0.30
    rerank_weight = 0.15
    if vector_score < RELEVANCE_THRESHOLDS["domain_vector"]:
        bm25_weight *= 0.35
        rerank_weight *= 0.55
    if float(query_quality.get("domainHitRate") or 0) < RELEVANCE_THRESHOLDS["intent_hit_rate"] and int(query_quality.get("strongDomainSignalCount") or 0) < 2:
        bm25_weight *= 0.5
        rerank_weight *= 0.65
    total = 0.0
    for name, weight in (("vector", vector_weight), ("bm25", bm25_weight), ("rerank", rerank_weight)):
        rank = rankings.get(name, {}).get(chunk_id)
        if rank:
            total += weight / (k + rank)
    return total * 100


def local_rerank_score(query: str, content: str) -> float:
    query_terms = tokenize(query)
    content_terms = tokenize(content)
    if not query_terms or not content_terms:
        return 0.0
    query_set = set(query_terms)
    content_set = set(content_terms)
    overlap = len(query_set & content_set) / max(1, len(query_set))
    phrase_bonus = 0.0
    compact_query = re.sub(r"\s+", "", query.lower())
    compact_content = re.sub(r"\s+", "", content.lower())
    for size in (8, 6, 4):
        phrases = {compact_query[i : i + size] for i in range(max(0, len(compact_query) - size + 1))}
        phrases.discard("")
        if phrases and any(phrase in compact_content for phrase in phrases):
            phrase_bonus += size / 20
            break
    return overlap + phrase_bonus
