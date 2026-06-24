import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.api.shared import user_payload
from backend.app.core.config import settings
from backend.app.core.network import forwarded_client_ip
from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.models.domain import User
from backend.app.services.runtime_metrics import record_runtime_failure


router = APIRouter(prefix="/api")
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_failed_logins: dict[str, tuple[int, float]] = {}
_login_state_lock = Lock()
_login_redis_client: Any | None = None
_login_redis_failed_at: float | None = None
_login_redis_client_lock = Lock()
LOGIN_ATTEMPTS_PER_MINUTE = 5
LOGIN_LOCKOUT_THRESHOLD = 10
LOGIN_LOCKOUT_SECONDS = 15 * 60
AUTH_COOKIE_NAME = "pinai_access_token"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1, description="密码不能为空")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


def _client_ip(request: Request) -> str:
    remote_host = request.client.host if request.client else "unknown"
    return forwarded_client_ip(remote_host, request.headers.get("x-forwarded-for"), settings.trusted_proxy_ips)


def _login_key(username: str, request: Request) -> str:
    return f"{username.strip().lower()}:{_client_ip(request)}"


def _login_user_key(username: str) -> str:
    return f"user:{username.strip().lower()}"


def _get_login_redis_client():
    global _login_redis_client, _login_redis_failed_at
    if not settings.redis_url:
        return None
    with _login_redis_client_lock:
        if _login_redis_client is not None:
            return _login_redis_client
        if _login_redis_failed_at and time.monotonic() - _login_redis_failed_at < 30:
            return None
        try:
            import redis

            _login_redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            _login_redis_client.ping()
            return _login_redis_client
        except Exception as exc:
            _login_redis_failed_at = time.monotonic()
            record_runtime_failure("redis_login_limiter_unavailable", exc)
            return None


def _redis_key(kind: str, key: str) -> str:
    return f"auth:login:{kind}:{key}"


def _assert_login_allowed_redis(key: str) -> bool | None:
    client = _get_login_redis_client()
    if client is None:
        return None
    now = time.time()
    attempts_key = _redis_key("attempts", key)
    lock_key = _redis_key("lock", key)
    try:
        locked_until = client.get(lock_key)
        if locked_until:
            retry_after = max(1, int(float(locked_until) - now))
            if retry_after > 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"登录失败次数过多，请 {retry_after} 秒后再试",
                    headers={"Retry-After": str(retry_after)},
                )
            client.delete(lock_key)

        member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
        pipe = client.pipeline()
        pipe.zremrangebyscore(attempts_key, 0, now - 60)
        pipe.zadd(attempts_key, {member: now})
        pipe.zcard(attempts_key)
        pipe.expire(attempts_key, 120)
        _, _, count, _ = pipe.execute()
        if int(count) > LOGIN_ATTEMPTS_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="登录尝试过于频繁，请稍后再试",
                headers={"Retry-After": "60"},
            )
        return True
    except HTTPException:
        raise
    except Exception as exc:
        record_runtime_failure("redis_login_limiter_failed", exc)
        return None


def _assert_login_lock_redis(key: str) -> bool | None:
    client = _get_login_redis_client()
    if client is None:
        return None
    now = time.time()
    lock_key = _redis_key("lock", key)
    try:
        locked_until = client.get(lock_key)
        if locked_until:
            retry_after = max(1, int(float(locked_until) - now))
            if retry_after > 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"登录失败次数过多，请 {retry_after} 秒后再试",
                    headers={"Retry-After": str(retry_after)},
                )
            client.delete(lock_key)
        return True
    except HTTPException:
        raise
    except Exception as exc:
        record_runtime_failure("redis_login_lock_check_failed", exc)
        return None


def _assert_login_allowed(key: str, username_key: str) -> None:
    redis_key_allowed = _assert_login_allowed_redis(key)
    redis_user_lock_allowed = _assert_login_lock_redis(username_key)
    if redis_key_allowed is True and redis_user_lock_allowed is True:
        return

    with _login_state_lock:
        now = time.monotonic()
        for lock_key in (key, username_key):
            failures, locked_until = _failed_logins.get(lock_key, (0, 0.0))
            if locked_until and now < locked_until:
                retry_after = max(1, int(locked_until - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"登录失败次数过多，请 {retry_after} 秒后再试",
                    headers={"Retry-After": str(retry_after)},
                )

        bucket = _login_attempts[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= LOGIN_ATTEMPTS_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="登录尝试过于频繁，请稍后再试",
                headers={"Retry-After": "60"},
            )
        bucket.append(now)


def _record_login_failure(key: str) -> None:
    client = _get_login_redis_client()
    if client is not None:
        try:
            failures = int(client.incr(_redis_key("failures", key)))
            client.expire(_redis_key("failures", key), LOGIN_LOCKOUT_SECONDS)
            if failures >= LOGIN_LOCKOUT_THRESHOLD:
                locked_until = time.time() + LOGIN_LOCKOUT_SECONDS
                client.setex(_redis_key("lock", key), LOGIN_LOCKOUT_SECONDS, str(locked_until))
            return
        except Exception as exc:
            record_runtime_failure("redis_login_failure_record_failed", exc)

    with _login_state_lock:
        now = time.monotonic()
        failures, _locked_until = _failed_logins.get(key, (0, 0.0))
        failures += 1
        locked_until = now + LOGIN_LOCKOUT_SECONDS if failures >= LOGIN_LOCKOUT_THRESHOLD else 0.0
        _failed_logins[key] = (failures, locked_until)


def _record_login_success(key: str) -> None:
    client = _get_login_redis_client()
    if client is not None:
        try:
            client.delete(_redis_key("attempts", key), _redis_key("failures", key), _redis_key("lock", key))
        except Exception as exc:
            record_runtime_failure("redis_login_success_cleanup_failed", exc)
    with _login_state_lock:
        _login_attempts.pop(key, None)
        _failed_logins.pop(key, None)


def _set_auth_cookie(response: Response, token: str) -> None:
    secure = settings.app_env.lower() in {"production", "prod", "staging"}
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


@router.post("/auth/login")
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    login_key = _login_key(req.username, request)
    username_key = _login_user_key(req.username)
    _assert_login_allowed(login_key, username_key)
    user = db.scalar(select(User).where(User.username == req.username))
    if not user or not user.is_active or not verify_password(req.password, user.hashed_password):
        _record_login_failure(login_key)
        _record_login_failure(username_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    _record_login_success(login_key)
    _record_login_success(username_key)
    token = create_access_token(subject=user.username, role_key=user.role.key)
    _set_auth_cookie(response, token)
    return {"accessToken": token, "tokenType": "bearer", "user": user_payload(user)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_payload(user)


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return {"ok": True}


@router.patch("/auth/password")
def change_password(req: PasswordChangeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(req.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    if req.current_password == req.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")
    user.hashed_password = hash_password(req.new_password)
    commit_or_rollback(db)
    return {"ok": True}

