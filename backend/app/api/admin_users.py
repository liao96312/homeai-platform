from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.api.routes._helpers import add_log, assert_admin
from backend.app.core.security import hash_password
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.models.domain import BusinessArtifact, KnowledgeDocument, RagQueryLog, Role, User


router = APIRouter(prefix="/api")


class UserCreateRequest(BaseModel):
    username: str
    full_name: str
    password: str
    role_key: str
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    role_key: str | None = None
    is_active: bool | None = None
    password: str | None = None


def managed_user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.full_name,
        "isActive": user.is_active,
        "role": {"key": user.role.key, "name": user.role.name, "color": user.role.color},
    }


@router.get("/admin/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_admin(user)
    users = db.scalars(select(User).order_by(User.id)).all()
    return {"users": [managed_user_payload(item) for item in users]}


@router.post("/admin/users")
def create_user(req: UserCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_admin(user)
    username = req.username.strip()
    full_name = req.full_name.strip()
    password = req.password.strip()
    if not username or not full_name or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名、姓名和密码不能为空")
    if len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少需要 6 位")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    role = db.scalar(select(Role).where(Role.key == req.role_key))
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    if role.key == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能通过用户管理创建超级管理员")
    new_user = User(
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        role_id=role.id,
        is_active=req.is_active,
    )
    db.add(new_user)
    add_log(db, "👤", "创建用户", f"{full_name} / {role.name} · 操作人：{user.full_name}", "green")
    commit_or_rollback(db)
    db.refresh(new_user)
    return managed_user_payload(new_user)


@router.patch("/admin/users/{user_id}")
def update_user(user_id: int, req: UserUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_admin(user)
    target = db.scalar(select(User).where(User.id == user_id))
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if req.full_name is not None:
        full_name = req.full_name.strip()
        if not full_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="姓名不能为空")
        target.full_name = full_name
    if req.role_key is not None:
        if target.id == user.id and req.role_key != user.role.key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能修改当前登录用户的角色")
        role = db.scalar(select(Role).where(Role.key == req.role_key))
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
        if role.key == "admin" and target.role.key != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能通过用户管理授予超级管理员角色")
        target.role_id = role.id
    if req.is_active is not None:
        if target.id == user.id and not req.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能停用当前登录用户")
        target.is_active = req.is_active
    if req.password is not None:
        password = req.password.strip()
        if len(password) < 6:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少需要 6 位")
        target.hashed_password = hash_password(password)
    add_log(db, "👤", "更新用户", f"{target.full_name} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    db.refresh(target)
    return managed_user_payload(target)


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_admin(user)
    target = db.scalar(select(User).where(User.id == user_id))
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if target.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录用户")
    title = f"{target.full_name} / @{target.username}"
    for doc in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.uploader_id == target.id)).all():
        doc.uploader_id = None
    for artifact in db.scalars(select(BusinessArtifact).where(BusinessArtifact.owner_id == target.id)).all():
        artifact.owner_id = None
    for log in db.scalars(select(RagQueryLog).where(RagQueryLog.user_id == target.id)).all():
        log.user_id = None
    db.delete(target)
    add_log(db, "🗑️", "删除用户", f"{title} · 操作人：{user.full_name}", "red")
    commit_or_rollback(db)
    return {"deleted": True, "userId": user_id}

