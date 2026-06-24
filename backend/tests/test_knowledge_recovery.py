from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.domain import KnowledgeBase, KnowledgeDocument
from backend.app.services import knowledge


def test_recover_pending_index_jobs_marks_missing_staged_file_failed(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        kb = KnowledgeBase(key="sales", name="销售库", description="", icon="", theme="blue")
        db.add(kb)
        db.flush()
        doc = KnowledgeDocument(
            kb_id=kb.id,
            filename="missing.pdf",
            content_type="application/pdf",
            status="queued",
            metadata_json={
                "upload_path": str(tmp_path / "missing.pdf"),
                "chunk_size": 800,
                "chunk_overlap": 120,
            },
        )
        db.add(doc)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(knowledge, "SessionLocal", Session)
    monkeypatch.setattr(knowledge.settings, "knowledge_async_indexing", True)
    monkeypatch.setattr(knowledge.settings, "knowledge_recover_pending_jobs_on_startup", True)

    scheduled = knowledge.recover_pending_index_jobs()

    db = Session()
    try:
        saved = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.filename == "missing.pdf"))
        assert scheduled == 0
        assert saved.status == "failed"
        assert saved.metadata_json["error"] == "staged_file_missing_on_startup"
    finally:
        db.close()


def test_recover_pending_index_jobs_schedules_existing_staged_file(monkeypatch, tmp_path):
    staged = tmp_path / "doc_1.txt"
    staged.write_text("hello", encoding="utf-8")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        kb = KnowledgeBase(key="sales", name="销售库", description="", icon="", theme="blue")
        db.add(kb)
        db.flush()
        doc = KnowledgeDocument(
            kb_id=kb.id,
            filename="doc.txt",
            content_type="text/plain",
            status="indexing",
            metadata_json={
                "upload_path": str(staged),
                "chunk_size": 321,
                "chunk_overlap": 12,
            },
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    submitted = []

    def fake_submit(doc_id_arg, path_arg, *, chunk_size, chunk_overlap):
        submitted.append((doc_id_arg, path_arg, chunk_size, chunk_overlap))

    monkeypatch.setattr(knowledge, "SessionLocal", Session)
    monkeypatch.setattr(knowledge.settings, "knowledge_async_indexing", True)
    monkeypatch.setattr(knowledge.settings, "knowledge_recover_pending_jobs_on_startup", True)
    monkeypatch.setattr(knowledge, "_submit_recovered_index_job", fake_submit)

    scheduled = knowledge.recover_pending_index_jobs()

    assert scheduled == 1
    assert submitted == [(doc_id, str(staged), 321, 12)]


def test_retry_document_index_rejects_missing_staged_file(tmp_path):
    doc = KnowledgeDocument(
        id=9,
        filename="missing.pdf",
        status="failed",
        metadata_json={"upload_path": str(tmp_path / "missing.pdf")},
    )

    try:
        knowledge.retry_document_index(doc)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
    else:
        raise AssertionError("missing staged file should reject retry")
    assert doc.status == "failed"
    assert doc.metadata_json["error"] == "staged_file_missing"
