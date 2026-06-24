import json
import logging
import time
from copy import deepcopy
from threading import Lock

from backend.app.core.config import settings

logger = logging.getLogger(__name__)
SEARCH_CACHE_TTL_SECONDS = settings.knowledge_search_cache_ttl_seconds
_SEARCH_CACHE: dict[str, tuple[float, list[dict]]] = {}
_SEARCH_CACHE_MAX_ITEMS = 512
_SEARCH_CACHE_LOCK = Lock()
_redis_search_cache_client = None
_redis_search_cache_failed_at: float | None = None
_redis_search_cache_client_lock = Lock()


def clear_search_cache(kb_key: str | None = None) -> None:
    with _SEARCH_CACHE_LOCK:
        if kb_key is None:
            _SEARCH_CACHE.clear()
            clear_redis_search_cache()
            return
        prefix = f"{kb_key}:"
        for key in list(_SEARCH_CACHE):
            if key.startswith(prefix):
                _SEARCH_CACHE.pop(key, None)
    clear_redis_search_cache(kb_key)


def get_search_cache_redis_client():
    global _redis_search_cache_client, _redis_search_cache_failed_at
    if not settings.redis_url:
        return None
    with _redis_search_cache_client_lock:
        if _redis_search_cache_client is not None:
            return _redis_search_cache_client
        if _redis_search_cache_failed_at and time.monotonic() - _redis_search_cache_failed_at < 30:
            return None
        try:
            import redis

            _redis_search_cache_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            _redis_search_cache_client.ping()
            logger.info("Redis knowledge search cache enabled")
            return _redis_search_cache_client
        except Exception:
            _redis_search_cache_failed_at = time.monotonic()
            logger.exception("Redis knowledge search cache unavailable; falling back to in-memory cache")
            return None


def redis_search_cache_key(cache_key: str) -> str:
    return f"kb_search:{cache_key}"


def get_cached_search_result(cache_key: str) -> list[dict] | None:
    client = get_search_cache_redis_client()
    if client is not None:
        try:
            raw = client.get(redis_search_cache_key(cache_key))
            if raw:
                payload = json.loads(raw)
                if isinstance(payload, list):
                    return deepcopy(payload)
        except Exception:
            logger.exception("Redis knowledge search cache read failed")

    now = time.monotonic()
    with _SEARCH_CACHE_LOCK:
        cached = _SEARCH_CACHE.get(cache_key)
        if cached and now - cached[0] <= SEARCH_CACHE_TTL_SECONDS:
            return deepcopy(cached[1])
        if cached:
            _SEARCH_CACHE.pop(cache_key, None)
    return None


def set_cached_search_result(cache_key: str, result: list[dict]) -> None:
    client = get_search_cache_redis_client()
    if client is not None:
        try:
            client.setex(
                redis_search_cache_key(cache_key),
                max(1, int(SEARCH_CACHE_TTL_SECONDS)),
                json.dumps(result, ensure_ascii=False),
            )
        except Exception:
            logger.exception("Redis knowledge search cache write failed")

    with _SEARCH_CACHE_LOCK:
        _SEARCH_CACHE[cache_key] = (time.monotonic(), deepcopy(result))
        if len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX_ITEMS:
            oldest_keys = sorted(_SEARCH_CACHE, key=lambda key: _SEARCH_CACHE[key][0])[:128]
            for old_key in oldest_keys:
                _SEARCH_CACHE.pop(old_key, None)


def clear_redis_search_cache(kb_key: str | None = None) -> None:
    client = get_search_cache_redis_client()
    if client is None:
        return
    pattern = "kb_search:*" if kb_key is None else f"kb_search:{kb_key}:*"
    try:
        keys = list(client.scan_iter(match=pattern, count=200))
        if keys:
            client.delete(*keys)
    except Exception:
        logger.exception("Redis knowledge search cache clear failed")

