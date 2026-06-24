import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal, commit_or_rollback
from backend.app.models.domain import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, User
from backend.app.services.document_parsing import extract_text
from backend.app.services.knowledge_cache import clear_search_cache, get_cached_search_result, set_cached_search_result
from backend.app.services.embeddings import (
    EMBEDDING_MODEL,
    cosine_similarity,
    embed_text,
    estimate_tokens,
)
from backend.app.services.knowledge_store import (
    get_kb_collection,
)
from backend.app.services.rag_gate import (
    RELEVANCE_THRESHOLDS,
    classify_rag_query,
    effective_query_terms,
)
from backend.app.services.runtime_metrics import record_runtime_failure
from backend.app.services.knowledge_scoring import (
    bm25_rank,
    build_relevance_evidence,
    defensive_rrf_score,
    escape_like,
    local_rerank_score,
    rank_scores,
)
from backend.app.services.text_chunking import split_text

logger = logging.getLogger(__name__)
_recovery_executor: ThreadPoolExecutor | None = None


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

async def index_upload(
    db: Session,
    kb: KnowledgeBase,
    user: User,
    file: UploadFile,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    auto_index: bool = True,
) -> KnowledgeDocument:
    raw = await file.read()
    validate_upload_size(raw)
    text = await run_in_threadpool(extract_text, file.filename or "upload.txt", raw)
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件未解析出有效文本")
    chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap) if auto_index else []
    if auto_index and not chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件未解析出有效文本")

    # --- SQL metadata ---
    doc = KnowledgeDocument(
        kb_id=kb.id,
        filename=file.filename or "upload.txt",
        content_type=file.content_type or "",
        status="indexed" if auto_index else "uploaded",
        char_count=len(text),
        chunk_count=len(chunks),
        uploader_id=user.id,
        metadata_json={"chunk_size": chunk_size, "chunk_overlap": chunk_overlap, "auto_index": auto_index},
    )
    db.add(doc)
    db.flush()

    if not auto_index:
        kb.docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
        kb.chunks = db.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.kb_id == kb.id)) or 0
        kb.updated_at_label = "刚刚"
        commit_or_rollback(db)
        db.refresh(doc)
        return doc

    embeddings = await run_in_threadpool(lambda: [embed_text(c) for c in chunks])
    for idx, chunk in enumerate(chunks):
        db.add(
            KnowledgeChunk(
                kb_id=kb.id,
                document_id=doc.id,
                chunk_index=idx,
                content=chunk,
                token_estimate=estimate_tokens(chunk),
                embedding_model=EMBEDDING_MODEL,
                embedding=[],
                metadata_json={"filename": doc.filename, "embeddingStoredIn": "chroma"},
            )
        )
    db.flush()

    # --- ChromaDB vector index ---
    try:
        collection = get_kb_collection(kb.key)
        collection.add(
            ids=[f"{kb.key}_{doc.id}_{idx}" for idx in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
            metadatas=[
                {
                    "chunk_id": chunk.id,
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in db.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.document_id == doc.id)
                    .order_by(KnowledgeChunk.chunk_index)
                ).all()
            ],
        )
    except Exception as exc:
        doc.status = "partial"
        doc.metadata_json = {
            **(doc.metadata_json or {}),
            "vector_index_status": "failed",
            "vector_index_error": type(exc).__name__,
        }
        record_runtime_failure("chroma_add_failed", exc)
        logging.getLogger(__name__).warning("ChromaDB add failed for kb=%s doc=%s", kb.key, doc.id, exc_info=True)

    # --- Stats ---
    kb.docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
    kb.chunks = db.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.kb_id == kb.id)) or 0
    kb.updated_at_label = "刚刚"
    commit_or_rollback(db)
    clear_search_cache(kb.key)
    db.refresh(doc)
    return doc


async def create_upload_job(
    db: Session,
    kb: KnowledgeBase,
    user: User,
    file: UploadFile,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    auto_index: bool = True,
) -> tuple[KnowledgeDocument, str]:
    raw = await file.read()
    validate_upload_size(raw)
    doc = KnowledgeDocument(
        kb_id=kb.id,
        filename=file.filename or "upload.txt",
        content_type=file.content_type or "",
        status="queued" if auto_index else "uploaded",
        char_count=0,
        chunk_count=0,
        uploader_id=user.id,
        metadata_json={
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "auto_index": auto_index,
            "file_size": len(raw),
            "indexing": "queued" if auto_index else "disabled",
        },
    )
    db.add(doc)
    db.flush()
    upload_path = ""
    if auto_index:
        upload_path = save_upload_staging_file(doc.id, doc.filename, raw)
        doc.metadata_json = {**(doc.metadata_json or {}), "upload_path": upload_path}
    kb.docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
    kb.updated_at_label = "刚刚"
    commit_or_rollback(db)
    db.refresh(doc)
    if not auto_index:
        return doc, ""
    return doc, upload_path


def validate_upload_size(raw: bytes) -> None:
    max_bytes = int(settings.knowledge_max_upload_bytes or 0)
    if max_bytes > 0 and len(raw) > max_bytes:
        max_mb = max_bytes / 1024 / 1024
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"单个文件暂限 {max_mb:.0f}MB",
        )


def save_upload_staging_file(doc_id: int, filename: str, raw: bytes) -> str:
    staging_dir = Path(settings.knowledge_upload_staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename or "upload.bin").suffix[:20]
    target = staging_dir / f"doc_{doc_id}{suffix}"
    target.write_bytes(raw)
    return str(target)


def delete_upload_staging_file(doc: KnowledgeDocument) -> None:
    path_value = str((doc.metadata_json or {}).get("upload_path") or "")
    if not path_value:
        return
    try:
        path = Path(path_value)
        staging_root = Path(settings.knowledge_upload_staging_dir).resolve()
        resolved = path.resolve()
        if staging_root == resolved or staging_root in resolved.parents:
            path.unlink(missing_ok=True)
    except Exception:
        logger.warning("Failed to delete staged upload for doc=%s", doc.id, exc_info=True)


def index_document_file_job(
    doc_id: int,
    upload_path: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> None:
    try:
        raw = Path(upload_path).read_bytes()
    except Exception as exc:
        record_runtime_failure("knowledge_upload_staging_read_failed", exc)
        db = SessionLocal()
        try:
            doc = db.get(KnowledgeDocument, doc_id)
            if doc:
                doc.status = "failed"
                doc.metadata_json = {**(doc.metadata_json or {}), "indexing": "failed", "error": "staged_file_missing"}
                commit_or_rollback(db)
        finally:
            db.close()
        return
    index_document_bytes_job(doc_id, raw, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def recover_pending_index_jobs() -> int:
    if not settings.knowledge_async_indexing or not settings.knowledge_recover_pending_jobs_on_startup:
        return 0
    db = SessionLocal()
    scheduled = 0
    try:
        docs = db.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.status.in_(["queued", "indexing"]))
            .order_by(KnowledgeDocument.id.asc())
        ).all()
        for doc in docs:
            metadata = dict(doc.metadata_json or {})
            upload_path = str(metadata.get("upload_path") or "")
            chunk_size = int(metadata.get("chunk_size") or 800)
            chunk_overlap = int(metadata.get("chunk_overlap") or 120)
            if not upload_path or not Path(upload_path).exists():
                doc.status = "failed"
                doc.metadata_json = {**metadata, "indexing": "failed", "error": "staged_file_missing_on_startup"}
                continue
            _submit_recovered_index_job(doc.id, upload_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            scheduled += 1
        if docs:
            commit_or_rollback(db)
    finally:
        db.close()
    if scheduled:
        logger.info("Recovered %d pending knowledge indexing job(s)", scheduled)
    return scheduled


def retry_document_index(doc: KnowledgeDocument) -> str:
    metadata = dict(doc.metadata_json or {})
    upload_path = str(metadata.get("upload_path") or "")
    if not upload_path or not Path(upload_path).exists():
        doc.status = "failed"
        doc.metadata_json = {**metadata, "indexing": "failed", "error": "staged_file_missing"}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="原始上传文件不存在，无法重试，请重新上传")
    chunk_size = int(metadata.get("chunk_size") or 800)
    chunk_overlap = int(metadata.get("chunk_overlap") or 120)
    doc.status = "queued"
    doc.metadata_json = {
        **metadata,
        "indexing": "queued",
        "error": "",
        "retry_count": int(metadata.get("retry_count") or 0) + 1,
    }
    _submit_recovered_index_job(doc.id, upload_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return upload_path


def _submit_recovered_index_job(doc_id: int, upload_path: str, *, chunk_size: int, chunk_overlap: int) -> None:
    global _recovery_executor
    if _recovery_executor is None:
        workers = max(1, min(int(settings.knowledge_recovery_max_workers or 1), 8))
        _recovery_executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="knowledge-index")
    _recovery_executor.submit(index_document_file_job, doc_id, upload_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def index_document_bytes_job(
    doc_id: int,
    raw: bytes,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> None:
    db = SessionLocal()
    try:
        doc = db.get(KnowledgeDocument, doc_id)
        if not doc:
            return
        kb = db.get(KnowledgeBase, doc.kb_id)
        if not kb:
            doc.status = "failed"
            doc.metadata_json = {**(doc.metadata_json or {}), "indexing": "failed", "error": "knowledge_base_missing"}
            commit_or_rollback(db)
            return

        doc.status = "indexing"
        doc.metadata_json = {**(doc.metadata_json or {}), "indexing": "running"}
        commit_or_rollback(db)

        text = extract_text(doc.filename or "upload.txt", raw)
        if not text.strip():
            doc.status = "failed"
            doc.metadata_json = {**(doc.metadata_json or {}), "indexing": "failed", "error": "empty_text"}
            commit_or_rollback(db)
            return

        chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not chunks:
            doc.status = "failed"
            doc.metadata_json = {**(doc.metadata_json or {}), "indexing": "failed", "error": "empty_chunks"}
            commit_or_rollback(db)
            return

        db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).delete(synchronize_session=False)
        embeddings = [embed_text(chunk) for chunk in chunks]
        chunk_rows = []
        for idx, chunk in enumerate(chunks):
            row = KnowledgeChunk(
                kb_id=kb.id,
                document_id=doc.id,
                chunk_index=idx,
                content=chunk,
                token_estimate=estimate_tokens(chunk),
                embedding_model=EMBEDDING_MODEL,
                embedding=[],
                metadata_json={"filename": doc.filename, "embeddingStoredIn": "chroma"},
            )
            db.add(row)
            chunk_rows.append(row)
        db.flush()

        vector_status = "ok"
        try:
            collection = get_kb_collection(kb.key)
            collection.delete(ids=[f"{kb.key}_{doc.id}_{idx}" for idx in range(len(chunks))])
            collection.add(
                ids=[f"{kb.key}_{doc.id}_{idx}" for idx in range(len(chunks))],
                documents=chunks,
                embeddings=embeddings,
                metadatas=[
                    {
                        "chunk_id": chunk.id,
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "chunk_index": chunk.chunk_index,
                    }
                    for chunk in chunk_rows
                ],
            )
        except Exception as exc:
            vector_status = "failed"
            record_runtime_failure("chroma_add_failed", exc)
            logger.warning("ChromaDB add failed for kb=%s doc=%s", kb.key, doc.id, exc_info=True)

        doc.status = "indexed" if vector_status == "ok" else "partial"
        doc.char_count = len(text)
        doc.chunk_count = len(chunks)
        doc.metadata_json = {
            **(doc.metadata_json or {}),
            "indexing": "completed",
            "vector_index_status": vector_status,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        kb.docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
        kb.chunks = db.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.kb_id == kb.id)) or 0
        kb.updated_at_label = "刚刚"
        clear_search_cache(kb.key)
        commit_or_rollback(db)
    except Exception as exc:
        db.rollback()
        record_runtime_failure("knowledge_async_index_failed", exc)
        logger.warning("Knowledge async indexing failed for doc=%s", doc_id, exc_info=True)
        doc = db.get(KnowledgeDocument, doc_id)
        if doc:
            doc.status = "failed"
            doc.metadata_json = {**(doc.metadata_json or {}), "indexing": "failed", "error": type(exc).__name__}
            commit_or_rollback(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Search (now powered by ChromaDB)
# ---------------------------------------------------------------------------

def search_chunks(db: Session, kb: KnowledgeBase, query: str, top_k: int = 5, gate: dict | None = None) -> list[dict]:
    query_gate = gate or classify_rag_query(query)
    if not query_gate["allowed"]:
        return []
    safe_top_k = max(1, min(top_k, 20))
    gate_reason = str(query_gate.get("reason") or "")
    # Cache scope is knowledge-base level. Route handlers must call the KB
    # access guard before reaching this function; within one KB, chunks are
    # currently assumed to have identical visibility. If document/chunk-level
    # ACLs are added later, include the subject/visibility version in this key.
    cache_hash = hashlib.sha256(f"{query.strip().lower()}|{safe_top_k}|{gate_reason}|{EMBEDDING_MODEL}".encode("utf-8")).hexdigest()[:24]
    cache_key = f"{kb.key}:{cache_hash}"
    cached = get_cached_search_result(cache_key)
    if cached is not None:
        return cached
    result = _search_chunks_uncached(db, kb, query, top_k=safe_top_k, gate=query_gate)
    set_cached_search_result(cache_key, result)
    return result


def fetch_chunks_by_ids(db: Session, kb: KnowledgeBase, chunk_ids: list[int]) -> dict[int, KnowledgeChunk]:
    if not chunk_ids:
        return {}
    chunks = db.scalars(
        select(KnowledgeChunk).where(
            KnowledgeChunk.kb_id == kb.id,
            KnowledgeChunk.embedding_model == EMBEDDING_MODEL,
            KnowledgeChunk.id.in_(chunk_ids),
        )
    ).all()
    return {chunk.id: chunk for chunk in chunks}


def fetch_bm25_candidate_chunks(db: Session, kb: KnowledgeBase, query: str, limit: int = 400) -> list[KnowledgeChunk]:
    terms = sorted(effective_query_terms(query), key=len, reverse=True)
    terms = [term[:64] for term in terms if len(term) >= 2][:8]
    if not terms:
        return []
    filters = [KnowledgeChunk.content.ilike(f"%{escape_like(term)}%", escape="\\") for term in terms]
    return db.scalars(
        select(KnowledgeChunk)
        .where(
            KnowledgeChunk.kb_id == kb.id,
            KnowledgeChunk.embedding_model == EMBEDDING_MODEL,
            or_(*filters),
        )
        .order_by(KnowledgeChunk.id.desc())
        .limit(max(1, min(limit, 1000)))
    ).all()


def fetch_recent_chunks(db: Session, kb: KnowledgeBase, limit: int = 400) -> list[KnowledgeChunk]:
    return db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.kb_id == kb.id, KnowledgeChunk.embedding_model == EMBEDDING_MODEL)
        .order_by(KnowledgeChunk.id.desc())
        .limit(max(1, min(limit, 1000)))
    ).all()


def _search_chunks_uncached(db: Session, kb: KnowledgeBase, query: str, top_k: int = 5, gate: dict | None = None) -> list[dict]:
    query_gate = gate or classify_rag_query(query)
    if not query_gate["allowed"]:
        return []
    top_k = max(1, min(top_k, 20))
    candidate_limit = max(top_k * 4, 20)
    query_embedding = embed_text(query)
    rows_by_id: dict[int, KnowledgeChunk] = {}
    candidates: dict[int, dict] = {}

    try:
        collection = get_kb_collection(kb.key)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_limit,
            include=["documents", "metadatas", "distances"],
        )
        if results["ids"] and results["ids"][0]:
            chroma_items = []
            missing_chunk_pairs: set[tuple[int, int]] = set()
            unresolved_items = []
            for i, _chroma_id in enumerate(results["ids"][0]):
                meta = (results["metadatas"][0] or [{}])[i] if results["metadatas"] else {}
                distance = (results["distances"][0] or [0])[i] if results["distances"] else 0
                vector_score = round(1.0 - distance, 4) if distance else 1.0
                chunk_id = meta.get("chunk_id")
                if chunk_id is None and meta.get("document_id") is not None:
                    pair = (int(meta.get("document_id")), int(meta.get("chunk_index", i)))
                    missing_chunk_pairs.add(pair)
                    unresolved_items.append((pair, vector_score, i, meta))
                    continue
                if chunk_id is None:
                    continue
                chroma_items.append((int(chunk_id), vector_score, i, meta))
            if missing_chunk_pairs:
                resolved_rows = []
                sorted_pairs = sorted(missing_chunk_pairs)
                batch_size = 500
                for start in range(0, len(sorted_pairs), batch_size):
                    pair_batch = sorted_pairs[start : start + batch_size]
                    resolved_rows.extend(
                        db.execute(
                            select(KnowledgeChunk.id, KnowledgeChunk.document_id, KnowledgeChunk.chunk_index).where(
                                KnowledgeChunk.kb_id == kb.id,
                                tuple_(KnowledgeChunk.document_id, KnowledgeChunk.chunk_index).in_(pair_batch),
                            )
                        ).all()
                    )
                resolved = {(int(document_id), int(chunk_index)): int(chunk_id) for chunk_id, document_id, chunk_index in resolved_rows}
                for pair, vector_score, i, meta in unresolved_items:
                    chunk_id = resolved.get(pair)
                    if chunk_id is not None:
                        chroma_items.append((chunk_id, vector_score, i, meta))
            chunk_ids = [item[0] for item in chroma_items]
            if chunk_ids:
                rows_by_id.update(fetch_chunks_by_ids(db, kb, chunk_ids))
            for chunk_id, vector_score, i, meta in chroma_items:
                row = rows_by_id.get(chunk_id)
                candidates[int(chunk_id)] = _candidate_from_chunk(
                    row,
                    vector_score=vector_score,
                    content=(results["documents"][0] or [""])[i] if results["documents"] else "",
                    metadata=meta,
                )
    except Exception as exc:
        record_runtime_failure("chroma_query_failed", exc)
        import logging
        logging.getLogger(__name__).warning("ChromaDB query failed for kb=%s, using SQL vectors", kb.key, exc_info=True)

    bm25_rows = fetch_bm25_candidate_chunks(db, kb, query, limit=max(candidate_limit * 20, 200))
    for chunk in bm25_rows:
        rows_by_id[chunk.id] = chunk

    if not candidates:
        vector_rows = bm25_rows or fetch_recent_chunks(db, kb, limit=max(candidate_limit * 20, 200))
        for chunk in vector_rows:
            rows_by_id[chunk.id] = chunk
    else:
        vector_rows = []

    if not candidates and vector_rows:
        vector_ranked = sorted(
            ((cosine_similarity(query_embedding, chunk.embedding or []), chunk) for chunk in vector_rows),
            key=lambda item: item[0],
            reverse=True,
        )[:candidate_limit]
        for vector_score, chunk in vector_ranked:
            candidates[chunk.id] = _candidate_from_chunk(chunk, vector_score=vector_score)

    bm25_pool = list({chunk.id: chunk for chunk in [*bm25_rows, *rows_by_id.values()]}.values())
    bm25_scores = bm25_rank(query, bm25_pool)
    for chunk_id, bm25_score in bm25_scores[:candidate_limit]:
        chunk = rows_by_id.get(chunk_id)
        if not chunk:
            continue
        candidate = candidates.get(chunk_id) or _candidate_from_chunk(chunk)
        candidate["bm25Score"] = bm25_score
        candidates[chunk_id] = candidate

    if not candidates:
        return []

    rerank_raw = {cid: local_rerank_score(query, item.get("content", "")) for cid, item in candidates.items()}
    rankings = {
        "vector": rank_scores({cid: item.get("vectorScore", 0.0) for cid, item in candidates.items()}),
        "bm25": rank_scores({cid: item.get("bm25Score", 0.0) for cid, item in candidates.items()}),
        "rerank": rank_scores(rerank_raw),
    }

    ranked = []
    for chunk_id, item in candidates.items():
        item["vectorScore"] = round(float(item.get("vectorScore", 0.0)), 4)
        item["bm25Score"] = round(float(item.get("bm25Score", 0.0)), 4)
        item["rerankScore"] = round(float(rerank_raw.get(chunk_id, 0.0)), 4)
        relevance = build_relevance_evidence(query, item, query_gate)
        item["relevance"] = relevance
        if not relevance["accepted"]:
            continue
        final_score = defensive_rrf_score(
            chunk_id,
            rankings,
            vector_score=item["vectorScore"],
            query_quality=query_gate.get("quality", {}),
        )
        item["score"] = round(float(final_score), 4)
        item["searchMode"] = "hybrid_rrf_guarded"
        item["fusion"] = {
            "method": "rrf",
            "vectorRank": rankings.get("vector", {}).get(chunk_id),
            "bm25Rank": rankings.get("bm25", {}).get(chunk_id),
            "rerankRank": rankings.get("rerank", {}).get(chunk_id),
            "bm25WeightSuppressed": item["vectorScore"] < RELEVANCE_THRESHOLDS["domain_vector"],
        }
        ranked.append(item)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def _candidate_from_chunk(
    chunk: KnowledgeChunk | None,
    vector_score: float = 0.0,
    content: str = "",
    metadata: dict | None = None,
) -> dict:
    metadata = metadata or {}
    if chunk:
        content = content or chunk.content
        metadata = {**(chunk.metadata_json or {}), **metadata}
        return {
            "score": 0.0,
            "vectorScore": float(vector_score or 0.0),
            "bm25Score": 0.0,
            "rerankScore": 0.0,
            "chunkId": chunk.id,
            "documentId": chunk.document_id,
            "filename": chunk.document.filename if chunk.document else metadata.get("filename", ""),
            "chunkIndex": chunk.chunk_index,
            "content": content,
            "metadata": metadata,
        }
    return {
        "score": 0.0,
        "vectorScore": float(vector_score or 0.0),
        "bm25Score": 0.0,
        "rerankScore": 0.0,
        "chunkId": metadata.get("chunk_id"),
        "documentId": metadata.get("document_id", 0),
        "filename": metadata.get("filename", ""),
        "chunkIndex": metadata.get("chunk_index", 0),
        "content": content,
        "metadata": metadata,
    }


