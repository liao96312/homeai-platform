from fastapi import Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.api.routes._helpers import add_log, require_roles, save_artifact
from backend.app.api.routes._routers import router
from backend.app.api.routes._wecom_helpers import assert_wecom_internal_token
from backend.app.api.schemas import VideoGenerationRequest, WecomVideoMaterialCleanupRequest
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.models.domain import User
from backend.app.services.video_generation import (
    cleanup_money_printer_video_materials,
    create_money_printer_video_task,
    get_money_printer_task,
    upload_money_printer_video_material,
    video_delivery_status,
)


@router.post("/video/generate")
def generate_video(req: VideoGenerationRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    subject = req.subject.strip()
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频主题不能为空")
    result = create_money_printer_video_task(subject, script=req.script, materials=req.materials)
    artifact = save_artifact(
        db,
        "video_generation",
        f"视频生成 · {subject[:40]}",
        req.script.strip() or subject,
        result,
        user,
        "confirmed",
    )
    add_log(db, "🎬", "提交视频生成", f"{subject[:80]} · 操作人：{user.full_name}", "purple")
    commit_or_rollback(db)
    return {**result, "artifactId": artifact.id, "artifactStatus": artifact.status}


@router.get("/video/tasks/{task_id}")
def video_task_status(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    return get_money_printer_task(task_id)


@router.get("/video/tasks/{task_id}/delivery")
def video_task_delivery(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    return video_delivery_status(task_id)


@router.get("/wecom/video-tasks/{task_id}/delivery")
def wecom_video_task_delivery(task_id: str, request: Request):
    assert_wecom_internal_token(request)
    return video_delivery_status(task_id)


@router.post("/wecom/video-materials")
async def upload_wecom_video_material(request: Request, file: UploadFile = File(...)):
    assert_wecom_internal_token(request)
    if file.size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="素材文件不能为空")
    return await upload_money_printer_video_material(file.filename or "material.bin", file.file)


@router.post("/wecom/video-materials/cleanup")
def cleanup_wecom_video_materials(req: WecomVideoMaterialCleanupRequest, request: Request):
    assert_wecom_internal_token(request)
    return cleanup_money_printer_video_materials(req.files)
