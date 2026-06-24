import logging
import hmac
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.app.api import admin_users, auth, conversations
from backend.app.api.deps import require_admin
from backend.app.api.routes import openai_router, router, wecom_router
from backend.app.core.chroma import get_chroma_client
from backend.app.core.config import settings, validate_runtime_settings
from backend.app.core.network import forwarded_client_ip
from backend.app.db.session import engine, get_db_context
from backend.app.models import domain  # noqa: F401
from backend.app.services.embeddings import check_local_embedding_ready
from backend.app.services.knowledge import recover_pending_index_jobs
from backend.app.services.llm import get_llm_provider
from backend.app.services.memory import memory_health
from backend.app.services.runtime_metrics import record_runtime_failure, runtime_metrics_snapshot
from backend.app.services.seed import seed_if_empty


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_rate_buckets_lock = Lock()
_redis_rate_client: Any | None = None
_redis_rate_failed_at: float | None = None
_redis_rate_client_lock = Lock()


def startup() -> None:
    validate_runtime_settings()
    wait_for_database()
    if settings.auto_migrate_on_startup:
        run_migrations()
    else:
        logger.info("Skipping Alembic migrations on startup because AUTO_MIGRATE_ON_STARTUP=false")
    with get_db_context() as db:
        seed_if_empty(db)
    recover_pending_index_jobs()


def wait_for_database() -> None:
    attempts = max(1, int(settings.db_startup_retry_attempts))
    delay = max(0.1, float(settings.db_startup_retry_delay_seconds))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("select 1"))
            if attempt > 1:
                logger.info("Database became ready after %d attempts", attempt)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            logger.warning("Database not ready (%s/%s): %s", attempt, attempts, type(exc).__name__)
            time.sleep(delay)
    raise RuntimeError(f"Database is not ready after {attempts} attempts") from last_error


def run_migrations() -> None:
    """Use Alembic in every environment so dev/test schemas do not drift."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    startup()
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/docs" if settings.expose_api_docs else None,
    redoc_url="/redoc" if settings.expose_api_docs else None,
    openapi_url="/openapi.json" if settings.expose_api_docs else None,
)


def client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def request_client_ip(request: Request) -> str:
    remote_host = client_host(request)
    return forwarded_client_ip(remote_host, request.headers.get("x-forwarded-for"), settings.trusted_proxy_ips)


def get_rate_limit_redis_client():
    global _redis_rate_client, _redis_rate_failed_at
    if not settings.redis_url:
        return None
    with _redis_rate_client_lock:
        if _redis_rate_client is not None:
            return _redis_rate_client
        if _redis_rate_failed_at and time.monotonic() - _redis_rate_failed_at < 30:
            return None
        try:
            import redis

            _redis_rate_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            _redis_rate_client.ping()
            logger.info("Redis rate limiter enabled")
            return _redis_rate_client
        except Exception as exc:
            _redis_rate_failed_at = time.monotonic()
            record_runtime_failure("redis_rate_limiter_unavailable", exc)
            logger.exception("Redis rate limiter unavailable; falling back to in-memory limiter")
            return None


def redis_rate_limit_exceeded(key: str, limit: int, now: float) -> bool | None:
    client = get_rate_limit_redis_client()
    if client is None:
        return None
    redis_key = f"rate:{key}"
    member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - 60)
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, 120)
        _, _, count, _ = pipe.execute()
        return int(count) > limit
    except Exception as exc:
        record_runtime_failure("redis_rate_limiter_failed", exc)
        logger.exception("Redis rate limiter failed; falling back to in-memory limiter")
        return None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)


def origin_allowed(origin: str, allowed_origins: list[str]) -> bool:
    try:
        parsed_origin = urlsplit(origin.rstrip("/"))
    except ValueError:
        return False
    if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.hostname:
        return False

    try:
        origin_port = parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
    except ValueError:
        return False
    origin_host = parsed_origin.hostname.lower()
    for allowed in allowed_origins:
        if not allowed:
            continue
        if allowed == "*":
            return settings.app_env.lower() not in {"production", "prod", "staging"}
        try:
            parsed_allowed = urlsplit(allowed.rstrip("/"))
        except ValueError:
            continue
        if parsed_allowed.scheme != parsed_origin.scheme or not parsed_allowed.hostname:
            continue
        try:
            allowed_port = parsed_allowed.port or (443 if parsed_allowed.scheme == "https" else 80)
        except ValueError:
            continue
        allowed_host = parsed_allowed.hostname.lower()
        if allowed_host.startswith("*."):
            suffix = allowed_host[1:]
            host_match = origin_host.endswith(suffix) and origin_host != allowed_host[2:]
        else:
            host_match = origin_host == allowed_host
        if host_match and origin_port == allowed_port:
            return True
    return False


@app.middleware("http")
async def csrf_origin_middleware(request: Request, call_next):
    """Reject browser write requests without a trusted Origin/Referer."""
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        # Bearer tokens are not automatically sent by browsers (no cookie auth),
        # so they are immune to CSRF and may bypass Origin validation.
        return await call_next(request)

    # The internal wecom token bypass is only honored when the provided value
    # matches the configured token. Previously ANY non-empty value bypassed the
    # check, allowing a browser attacker to set x-homeai-wecom-token: x and skip
    # Origin validation entirely.
    configured_wecom_token = (settings.wecom_internal_token or "").strip()
    provided_wecom_token = request.headers.get("x-homeai-wecom-token", "").strip()
    origin_header = request.headers.get("origin") or request.headers.get("referer", "")
    if (
        configured_wecom_token
        and provided_wecom_token
        and hmac.compare_digest(provided_wecom_token, configured_wecom_token)
        and not origin_header
        and request.url.path.startswith("/api/wecom/")
    ):
        return await call_next(request)

    origin = origin_header
    if not origin:
        logger.warning("csrf_origin_missing path=%s method=%s", request.url.path, request.method)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "缺少 Origin/Referer，写请求已被拒绝", "code": "csrf_origin_missing"},
        )

    if not origin_allowed(origin, settings.cors_origins):
        logger.warning("csrf_origin_mismatch origin=%s path=%s method=%s", origin, request.url.path, request.method)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "跨站请求已被拒绝", "code": "csrf_origin_mismatch"},
        )
    return await call_next(request)


@app.middleware("http")
async def request_body_size_middleware(request: Request, call_next):
    limit = request_body_size_limit(request)
    if limit > 0 and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        content_length = request.headers.get("content-length")
        try:
            body_size = int(content_length or "0")
        except ValueError:
            body_size = 0
        if body_size > limit:
            return JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": "请求体过大", "code": "request_body_too_large"},
            )
    return await call_next(request)


def request_body_size_limit(request: Request) -> int:
    path = request.url.path.rstrip("/")
    if (
        request.method.upper() == "POST"
        and path.startswith("/api/knowledge/")
        and path.endswith("/documents")
    ):
        multipart_overhead = 10 * 1024 * 1024
        return int(settings.knowledge_max_upload_bytes or 0) + multipart_overhead
    return int(settings.max_request_body_bytes or 0)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request_failed request_id=%s method=%s path=%s elapsed_ms=%s",
            request_id,
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = str(elapsed_ms)
    log_method = logger.warning if elapsed_ms >= settings.slow_request_ms else logger.info
    log_method(
        "request_complete request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not hasattr(request.state, "request_id"):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    if request.method == "OPTIONS" or request.url.path.startswith("/health"):
        return await call_next(request)
    now_monotonic = time.monotonic()
    now_epoch = time.time()
    ai_path = request.url.path in {"/api/chat/completions", "/v1/chat/completions", "/api/promo/copy"}
    limit = settings.ai_rate_limit_per_minute if ai_path else settings.api_rate_limit_per_minute
    if limit > 0:
        client_ip = request_client_ip(request)
        key = f"{client_ip or 'unknown'}:{'ai' if ai_path else 'api'}"
        redis_limited = redis_rate_limit_exceeded(key, limit, now_epoch)
        if redis_limited is None:
            with _rate_buckets_lock:
                bucket = _rate_buckets[key]
                while bucket and now_monotonic - bucket[0] >= 60:
                    bucket.popleft()
                limited = len(bucket) >= limit
                if not limited:
                    bucket.append(now_monotonic)
        else:
            limited = redis_limited
        if limited:
            logger.warning(
                "rate_limited client=%s path=%s limit=%d/%ds",
                client_ip,
                request.url.path,
                limit,
                60,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "请求过于频繁，请稍后再试", "code": "rate_limited", "requestId": getattr(request.state, "request_id", None)},
            )
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": "http_error", "requestId": request_id},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "code": "validation_error", "requestId": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    logger.exception("Unhandled request error request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "服务内部错误", "code": "internal_error", "requestId": request_id},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/detail")
def health_detail(_: object = Depends(require_admin)):
    # Internal diagnostic info (DB dialect, model names, persist dir, etc.).
    # Requires admin auth so anonymous callers cannot enumerate internals.
    checks = {
        "database": {"ok": False, "dialect": engine.dialect.name},
        "vectorStore": {"ok": False, "provider": "chroma", "persistDir": settings.chroma_persist_dir},
        "llm": {"ok": False, "provider": settings.ai_provider, "model": settings.deepseek_default_model},
        "embedding": {"ok": False, "provider": settings.embedding_provider, "model": settings.embedding_model, "cacheDir": settings.embedding_cache_dir},
        "memory": memory_health(),
        "runtimeMetrics": {"ok": True, **runtime_metrics_snapshot()},
    }
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        checks["database"]["ok"] = True
    except Exception as exc:
        checks["database"]["error"] = type(exc).__name__
    try:
        client = get_chroma_client()
        heartbeat = getattr(client, "heartbeat", None)
        if callable(heartbeat):
            heartbeat()
        checks["vectorStore"]["ok"] = True
    except Exception as exc:
        checks["vectorStore"]["error"] = type(exc).__name__
    try:
        checks["llm"] = get_llm_provider().health()
    except Exception as exc:
        checks["llm"] = {"ok": False, "provider": settings.ai_provider, "model": settings.deepseek_default_model, "error": type(exc).__name__}

    # ⚠️ 注意：embedding 首次加载模型可能耗时数秒，健康检查会等待加载完成
    checks["embedding"] = check_local_embedding_ready()
    status_value = "ok" if all(item.get("ok") for item in checks.values()) else "degraded"
    return {"status": status_value, "checks": checks}


app.include_router(auth.router)
app.include_router(admin_users.router)
app.include_router(router)
app.include_router(conversations.router)
app.include_router(openai_router)
app.include_router(wecom_router)
