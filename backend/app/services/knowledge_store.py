import logging

import chromadb
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.chroma import get_chroma_client
from backend.app.models.domain import KnowledgeBase, KnowledgePermission, Role, User

logger = logging.getLogger(__name__)


def get_kb_collection(kb_key: str) -> chromadb.Collection:
    """Get or create the ChromaDB collection for a knowledge base."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=f"kb_{kb_key}",
        metadata={"hnsw:space": "cosine"},
    )


def get_kb_or_404(db: Session, kb_key: str) -> KnowledgeBase:
    kb = db.scalar(select(KnowledgeBase).where(KnowledgeBase.key == kb_key))
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return kb


def delete_kb_collection(kb_key: str) -> None:
    try:
        get_chroma_client().delete_collection(name=f"kb_{kb_key}")
    except Exception as exc:
        logger.warning("Failed to delete Chroma collection for kb=%s: %s", kb_key, exc, exc_info=True)


def get_permission(db: Session, kb: KnowledgeBase, user: User) -> KnowledgePermission | None:
    return db.scalar(
        select(KnowledgePermission)
        .join(Role, KnowledgePermission.role_id == Role.id)
        .where(KnowledgePermission.kb_id == kb.id, Role.key == user.role.key)
    )


def assert_kb_access(db: Session, kb: KnowledgeBase, user: User, action: str) -> None:
    if user.role.key == "admin":
        return
    perm = get_permission(db, kb, user)
    allowed = {
        "view": bool(perm and perm.can_view),
        "edit": bool(perm and perm.can_edit),
        "manage": bool(perm and perm.can_manage),
    }
    if not allowed.get(action, False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权操作该知识库")
