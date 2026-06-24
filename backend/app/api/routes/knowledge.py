import logging

from fastapi import BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.core.config import settings
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.api.schemas import KnowledgeSearchRequest
from backend.app.api.shared import pagination
from backend.app.models.domain import KnowledgeChunk, KnowledgeDocument, RagQueryLog, User
from backend.app.services.chat import (
    RAG_STATUS_HIT, RAG_STATUS_MAYBE, RAG_STATUS_MISS, evaluate_retrieval,
)
from backend.app.services.embeddings import EMBEDDING_MODEL
from backend.app.services.knowledge import create_upload_job, delete_upload_staging_file, index_document_file_job, index_upload, retry_document_index, search_chunks
from backend.app.services.knowledge_cache import clear_search_cache
from backend.app.services.knowledge_store import assert_kb_access, get_kb_collection, get_kb_or_404
from backend.app.services.rag_gate import classify_rag_query, rag_gate_observation
from backend.app.api.routes._routers import router
from backend.app.api.routes._helpers import add_log, config_enabled


@router.post("/knowledge/{kb_key}/documents")
async def upload_knowledge_document(
    kb_key: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(120),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = get_kb_or_404(db, kb_key)
    assert_kb_access(db, kb, user, "edit")
    auto_index = config_enabled(db, "kb_auto_sync", True)
    if settings.knowledge_async_indexing:
        doc, upload_path = await create_upload_job(
            db,
            kb,
            user,
            file,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            auto_index=auto_index,
        )
        if upload_path:
            background_tasks.add_task(
                index_document_file_job,
                doc.id,
                upload_path,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        return {
            "id": doc.id,
            "kbKey": kb.key,
            "filename": doc.filename,
            "status": doc.status,
            "charCount": doc.char_count,
            "chunkCount": doc.chunk_count,
            "embeddingModel": EMBEDDING_MODEL,
            "async": True,
            "message": "文档已进入后台索引队列",
        }
    doc = await index_upload(
        db,
        kb,
        user,
        file,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        auto_index=auto_index,
    )
    return {
        "id": doc.id,
        "kbKey": kb.key,
        "filename": doc.filename,
        "status": doc.status,
        "charCount": doc.char_count,
        "chunkCount": doc.chunk_count,
        "embeddingModel": EMBEDDING_MODEL,
    }


@router.get("/knowledge/{kb_key}/documents")
def list_knowledge_documents(
    kb_key: str,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = get_kb_or_404(db, kb_key)
    assert_kb_access(db, kb, user, "view")
    safe_limit, safe_offset = pagination(limit, offset)
    total = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
    docs = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.kb_id == kb.id)
        .order_by(KnowledgeDocument.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
    ).all()
    return {
        "kbKey": kb.key,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "documents": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "status": doc.status,
                "charCount": doc.char_count,
                "chunkCount": doc.chunk_count,
                "contentType": doc.content_type,
                "metadata": doc.metadata_json,
            }
            for doc in docs
        ],
    }


@router.post("/knowledge/{kb_key}/search")
def search_knowledge(kb_key: str, req: KnowledgeSearchRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = get_kb_or_404(db, kb_key)
    assert_kb_access(db, kb, user, "view")
    if not req.query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="检索问题不能为空")
    gate = classify_rag_query(req.query)
    results = search_chunks(db, kb, req.query, top_k=req.top_k)
    retrieval = evaluate_retrieval(results, gate)
    if not gate.get("allowed") or retrieval.get("level") == "miss":
        rag_status = {**RAG_STATUS_MISS, "reason": gate.get("reason") or retrieval.get("reason")}
    elif retrieval.get("level") == "hit":
        rag_status = {**RAG_STATUS_HIT, "reason": retrieval.get("reason")}
    else:
        rag_status = {**RAG_STATUS_MAYBE, "reason": retrieval.get("reason")}
    gate_observation = rag_gate_observation(gate)
    top_sources = [
        {
            "rank": item.get("rank", index + 1),
            "kbKey": kb.key,
            "kbName": kb.name,
            "filename": item.get("filename"),
            "chunkId": item.get("chunkId"),
            "score": item.get("score"),
            "vectorScore": item.get("vectorScore"),
            "bm25Score": item.get("bm25Score"),
            "rerankScore": item.get("rerankScore"),
            "searchMode": item.get("searchMode"),
            "fusion": item.get("fusion"),
            "relevance": item.get("relevance"),
            "ragStatus": rag_status,
            "ragGate": gate_observation,
        }
        for index, item in enumerate(results)
    ] or [{"type": "status", "ragStatus": rag_status, "ragGate": gate_observation}]
    db.add(
        RagQueryLog(
            user_id=user.id,
            conversation_key=kb.key,
            query=req.query[:2000],
            top_k=req.top_k,
            hit_count=len(results),
            injected=False,
            top_sources=top_sources,
            created_at_label="刚刚",
        )
    )
    commit_or_rollback(db)
    return {
        "kbKey": kb.key,
        "query": req.query,
        "ragGate": gate,
        "retrieval": retrieval,
        "ragStatus": rag_status,
        "results": results,
    }


@router.delete("/knowledge/{kb_key}/documents/{doc_id}")
def delete_knowledge_document(kb_key: str, doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = get_kb_or_404(db, kb_key)
    assert_kb_access(db, kb, user, "edit")
    doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id, KnowledgeDocument.kb_id == kb.id))
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    delete_upload_staging_file(doc)
    # Delete chunks (SQL + ChromaDB)
    chunks = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)).all()
    if chunks:
        try:
            coll = get_kb_collection(kb.key)
            coll.delete(ids=[f"{kb.key}_{doc_id}_{c.chunk_index}" for c in chunks])
        except Exception:
            logging.getLogger(__name__).warning(
                "ChromaDB delete failed for kb=%s doc=%s (chunks will be cleaned from SQL only)",
                kb.key,
                doc_id,
                exc_info=True,
            )
        for c in chunks:
            db.delete(c)
    db.delete(doc)
    # Update stats
    kb.docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
    kb.chunks = db.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.kb_id == kb.id)) or 0
    clear_search_cache(kb.key)
    add_log(db, "🗑️", "删除文档", f"已从 {kb.name} 删除 {doc.filename} · 操作人：{user.full_name}", "red")
    commit_or_rollback(db)
    return {"deleted": True, "docId": doc_id, "kbKey": kb.key}


@router.post("/knowledge/{kb_key}/documents/{doc_id}/retry")
def retry_knowledge_document(kb_key: str, doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = get_kb_or_404(db, kb_key)
    assert_kb_access(db, kb, user, "edit")
    doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id, KnowledgeDocument.kb_id == kb.id))
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    if doc.status in {"queued", "indexing"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文档正在索引中，无需重复重试")
    retry_document_index(doc)
    commit_or_rollback(db)
    return {
        "id": doc.id,
        "kbKey": kb.key,
        "filename": doc.filename,
        "status": doc.status,
        "charCount": doc.char_count,
        "chunkCount": doc.chunk_count,
        "embeddingModel": EMBEDDING_MODEL,
        "async": True,
        "message": "文档已重新进入后台索引队列",
    }


