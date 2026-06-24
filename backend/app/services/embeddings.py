import hashlib
import logging
import math
import os
import re
import time
from threading import Lock
from typing import Iterable

from fastapi import HTTPException, status

from backend.app.core.config import settings

logger = logging.getLogger(__name__)
EMBEDDING_DIM = 384
EMBEDDING_MODEL = settings.embedding_model
_embedding_model = None
_embedding_failed_at: float | None = None
_EMBEDDING_RETRY_COOLDOWN_SECONDS: float = 30.0
_embedding_model_lock = Lock()




# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_text(text: str) -> list[float]:
    global _embedding_failed_at, _embedding_model
    provider = settings.embedding_provider.lower().strip()
    if provider == "hash":
        return embed_text_hash(text)
    if provider != "fastembed":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="当前仅支持 fastembed 或 hash embedding 模型")

    # Auto-retry after cooldown: don't permanently lock out on transient failures
    with _embedding_model_lock:
        if _embedding_failed_at is not None:
            elapsed = time.monotonic() - _embedding_failed_at
            if elapsed < _EMBEDDING_RETRY_COOLDOWN_SECONDS:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=local_embedding_not_ready_message(),
                )
            # Cooldown expired: reset model so we retry loading on next attempt.
            logger.info(
                "Embedding retry cooldown elapsed (%.1fs), attempting reload of %s",
                elapsed,
                settings.embedding_model,
            )
            _embedding_failed_at = None
            _embedding_model = None

    try:
        return embed_text_fastembed(text)
    except HTTPException:
        raise
    except Exception as exc:
        with _embedding_model_lock:
            _embedding_failed_at = time.monotonic()
            _embedding_model = None  # force reload on next attempt
        logger.warning(
            "Local fastembed model is unavailable (will retry after %.0fs)",
            _EMBEDDING_RETRY_COOLDOWN_SECONDS,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=local_embedding_not_ready_message(),
        ) from exc


def embed_text_fastembed(text: str) -> list[float]:
    global _embedding_model
    with _embedding_model_lock:
        if _embedding_model is None:
            if settings.hf_endpoint:
                os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
            from fastembed import TextEmbedding

            _embedding_model = TextEmbedding(
                model_name=settings.embedding_model,
                cache_dir=settings.embedding_cache_dir,
                local_files_only=not settings.embedding_allow_download,
            )
        vector = next(_embedding_model.embed([text]))
    return [round(float(v), 6) for v in vector.tolist()]


def local_embedding_not_ready_message() -> str:
    return (
        "本地 embedding 模型未就绪。请先运行 scripts/init-embedding.ps1 下载到本地缓存，"
        f"或配置 EMBEDDING_CACHE_DIR；当前模型={settings.embedding_model}，缓存目录={settings.embedding_cache_dir}"
    )


def check_local_embedding_ready() -> dict:
    try:
        vector = embed_text_fastembed("embedding health check")
        return {"ok": True, "provider": "fastembed", "model": settings.embedding_model, "cacheDir": settings.embedding_cache_dir, "dim": len(vector)}
    except Exception as exc:
        return {
            "ok": False,
            "provider": "fastembed",
            "model": settings.embedding_model,
            "cacheDir": settings.embedding_cache_dir,
            "error": type(exc).__name__,
        }


def embed_text_hash(text: str) -> list[float]:
    if not settings.hash_embedding_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HASH_EMBEDDING_KEY must be configured when EMBEDDING_PROVIDER=hash",
        )
    vector = [0.0] * EMBEDDING_DIM
    tokens = tokenize(text)
    if not tokens:
        tokens = [text[:64] or "empty"]
    hash_key = settings.hash_embedding_key.encode("utf-8")
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16, key=hash_key).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vector[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


def tokenize(text: str) -> list[str]:
    lower = text.lower()
    words = re.findall(r"[a-z0-9_]{2,}", lower)
    chinese = re.findall(r"[\u4e00-\u9fff]", lower)
    chinese_ngrams = []
    max_ngrams = 600
    for size, step in ((2, 1), (3, 2), (4, 4)):
        if len(chinese_ngrams) >= max_ngrams:
            break
        for i in range(0, max(0, len(chinese) - size + 1), step):
            chinese_ngrams.append("".join(chinese[i : i + size]))
            if len(chinese_ngrams) >= max_ngrams:
                break
    return words + chinese_ngrams


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    l_values = list(left)
    r_values = list(right)
    if not l_values or not r_values:
        return 0.0
    size = min(len(l_values), len(r_values))
    dot = sum(l_values[i] * r_values[i] for i in range(size))
    l_norm = math.sqrt(sum(v * v for v in l_values[:size])) or 1.0
    r_norm = math.sqrt(sum(v * v for v in r_values[:size])) or 1.0
    return dot / (l_norm * r_norm)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 3)

