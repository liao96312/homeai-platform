from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.api.payloads import artifact_payload, publish_job_payload
from backend.app.api.schemas import PublishRequest
from backend.app.api.shared import pagination
from backend.app.models.domain import PublishJob, User
from backend.app.services.publishing import publish_via_multipost
from backend.app.api.routes._routers import router
from backend.app.api.routes._helpers import (
    add_log, config_enabled, get_owned_artifact_or_404, get_publish_job_or_404,
    persist_publish_job, save_artifact,
)


@router.post("/publish/jobs")
def create_publish_jobs(req: PublishRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    title = req.title.strip()
    content = req.content.strip()
    platforms = [item.strip() for item in req.platforms if item and item.strip()]
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发布标题不能为空")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发布正文不能为空")
    if not platforms:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择一个发布平台")
    if req.scheduled_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="定时发布暂未启用，请直接创建即时发布任务")

    artifact = get_owned_artifact_or_404(db, req.artifact_id, user) if req.artifact_id else None
    if not artifact:
        artifact = save_artifact(
            db,
            "promo_copy",
            f"发布任务 · {title}",
            content,
            {"platforms": platforms, "title": title, "body": content, "source": req.source, "images": req.images, "videos": req.videos},
            user,
            "confirmed",
        )
    if config_enabled(db, "manual_publish_confirm", False) and artifact.status not in {"confirmed", "completed"}:
        artifact.status = "confirmed"
        artifact.result_json = {
            **(artifact.result_json or {}),
            "publishReview": {
                "required": True,
                "platforms": platforms,
                "title": title,
                "source": req.source,
            },
        }
        add_log(db, "🛂", "发布等待人工确认", f"{title} / {', '.join(platforms)} · 操作人：{user.full_name}", "orange")
        commit_or_rollback(db)
        db.refresh(artifact)
        return {
            "artifact": artifact_payload(artifact),
            "jobs": [],
            "requiresReview": True,
            "message": "发布前需要人工确认，请先确认产物后再创建发布任务",
        }
    jobs = [
        persist_publish_job(
            db,
            artifact=artifact,
            user=user,
            platform=platform,
            title=title,
            content=content,
            tags=req.tags,
            images=req.images,
            videos=req.videos,
        )
        for platform in platforms
    ]
    statuses = {job.status for job in jobs}
    if "needs_config" in statuses:
        artifact.status = "draft"
    elif statuses and statuses.issubset({"completed"}):
        artifact.status = "completed"
    elif "failed" in statuses:
        artifact.status = "confirmed"
    else:
        artifact.status = "confirmed"
    artifact.result_json = {
        **(artifact.result_json or {}),
        "publishJobs": [publish_job_payload(job) for job in jobs],
        "publishProvider": "multipost",
    }
    add_log(db, "📣", "创建发布任务", f"{title} / {', '.join(platforms)} · 操作人：{user.full_name}", "green")
    commit_or_rollback(db)
    for job in jobs:
        db.refresh(job)
    db.refresh(artifact)
    return {
        "artifact": artifact_payload(artifact),
        "jobs": [publish_job_payload(job) for job in jobs],
        "requiresReview": False,
        "scheduled": False,
    }


@router.get("/publish/jobs")
def list_publish_jobs(limit: int = 50, offset: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(PublishJob)
    if user.role.key != "admin":
        query = query.where(PublishJob.user_id == user.id)
    safe_limit, safe_offset = pagination(limit, offset)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(PublishJob.id.desc()).offset(safe_offset).limit(safe_limit)
    return {"jobs": [publish_job_payload(job) for job in db.scalars(query).all()], "total": total, "limit": safe_limit, "offset": safe_offset}


@router.post("/publish/jobs/{job_id}/retry")
def retry_publish_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = get_publish_job_or_404(db, job_id, user)
    result = publish_via_multipost(title=job.title, content=job.content, platform_label=job.platform_label)
    job.status = result.status
    job.platform_code = result.platform_code
    job.external_task_id = result.external_task_id
    job.request_json = result.request_payload or {}
    job.response_json = result.response_payload or {}
    job.error = result.error
    job.updated_at_label = "刚刚"
    add_log(db, "📣", "重试发布任务", f"{job.platform_label} / {job.title} · 操作人：{user.full_name}", "orange")
    commit_or_rollback(db)
    db.refresh(job)
    return publish_job_payload(job)


