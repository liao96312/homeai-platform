from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import decode_access_token
from backend.app.db.session import get_db
from backend.app.models.domain import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Browser sessions use the httpOnly cookie set by /api/auth/login so the
    # token is not exposed to JavaScript. API clients and OpenAI-compatible
    # callers may still pass Authorization: Bearer. CSRF checks in main.py
    # distinguish these paths: Bearer requests bypass Origin validation, cookie
    # requests do not.
    token = token or request.cookies.get("homeai_access_token")
    if not token:
        raise credentials_error
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise credentials_error
    username = payload.get("sub")
    if not username:
        raise credentials_error
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.is_active:
        raise credentials_error
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role.key != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")
    return user
