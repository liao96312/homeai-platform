from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.api.payloads import artifact_payload
from backend.app.api.schemas import ArtifactCreateRequest, ArtifactUpdateRequest
from backend.app.api.shared import pagination
from backend.app.models.domain import BusinessArtifact, User
from backend.app.api.routes._routers import router
from backend.app.api.routes._helpers import (
    add_log, get_artifact_or_404, save_artifact,
    validate_artifact_status,
)


@router.get("/artifacts")
def list_artifacts(
    artifact_type: str | None = None,
    limit: int = 30,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(BusinessArtifact)
    if artifact_type:
        query = query.where(BusinessArtifact.artifact_type == artifact_type)
    if user.role.key != "admin":
        if artifact_type == "design_card" and user.role.key == "design_manager":
            pass
        else:
            query = query.where(BusinessArtifact.owner_id == user.id)
    safe_limit, safe_offset = pagination(limit, offset)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(BusinessArtifact.id.desc()).offset(safe_offset).limit(safe_limit)
    return {"artifacts": [artifact_payload(item) for item in db.scalars(query).all()], "total": total, "limit": safe_limit, "offset": safe_offset}


@router.post("/artifacts")
def create_artifact(req: ArtifactCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not req.title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空")
    artifact = save_artifact(db, req.artifact_type, req.title, req.source, req.result, user, req.status)
    add_log(db, "🗂️", "保存业务产物", f"{req.artifact_type} / {req.title} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    db.refresh(artifact)
    return artifact_payload(artifact)

@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return artifact_payload(get_artifact_or_404(db, artifact_id, user))


@router.patch("/artifacts/{artifact_id}")
def update_artifact(
    artifact_id: int,
    req: ArtifactUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    artifact = get_artifact_or_404(db, artifact_id, user)
    if req.title is not None:
        clean_title = req.title.strip()
        if not clean_title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空")
        artifact.title = clean_title[:160]
    if req.status is not None:
        artifact.status = validate_artifact_status(req.status)
    if req.result is not None:
        artifact.result_json = req.result
    add_log(db, "🗂️", "更新业务产物", f"{artifact.title} 状态={artifact.status} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    db.refresh(artifact)
    return artifact_payload(artifact)


@router.delete("/artifacts/{artifact_id}")
def delete_artifact(artifact_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    artifact = get_artifact_or_404(db, artifact_id, user)
    title = artifact.title
    db.delete(artifact)
    add_log(db, "🗑️", "删除业务产物", f"{title} · 操作人：{user.full_name}", "red")
    commit_or_rollback(db)
    return {"deleted": True, "artifactId": artifact_id}

