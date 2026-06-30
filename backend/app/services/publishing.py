from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


PLATFORM_CODE_MAP = {
    "小红书": "DYNAMIC_REDNOTE",
    "rednote": "DYNAMIC_REDNOTE",
    "xiaohongshu": "DYNAMIC_REDNOTE",
    "抖音": "DYNAMIC_DOUYIN",
    "douyin": "DYNAMIC_DOUYIN",
    "微博": "DYNAMIC_WEIBO",
    "weibo": "DYNAMIC_WEIBO",
    "知乎": "DYNAMIC_ZHIHU",
    "zhihu": "DYNAMIC_ZHIHU",
    "公众号": "DYNAMIC_WEIXIN",
    "微信公众号": "DYNAMIC_WEIXIN",
    "微信": "DYNAMIC_WEIXIN",
    "朋友圈": "DYNAMIC_WEIXIN",
    "视频号": "DYNAMIC_WEIXINCHANNEL",
}


@dataclass
class PublishResult:
    status: str
    provider: str
    platform_code: str
    external_task_id: str = ""
    request_payload: dict | None = None
    response_payload: dict | None = None
    error: str = ""


def resolve_platform_code(label: str) -> str:
    clean = str(label or "").strip()
    lower = clean.lower()
    if clean in PLATFORM_CODE_MAP:
        return PLATFORM_CODE_MAP[clean]
    if lower in PLATFORM_CODE_MAP:
        return PLATFORM_CODE_MAP[lower]
    if "小红" in clean or "红书" in clean:
        return "DYNAMIC_REDNOTE"
    if "抖" in clean:
        return "DYNAMIC_DOUYIN"
    if "微博" in clean:
        return "DYNAMIC_WEIBO"
    if "知乎" in clean:
        return "DYNAMIC_ZHIHU"
    if "视频号" in clean:
        return "DYNAMIC_WEIXINCHANNEL"
    if "公众号" in clean or "微信" in clean or "朋友圈" in clean:
        return "DYNAMIC_WEIXIN"
    return clean if clean.startswith("DYNAMIC_") else "DYNAMIC_REDNOTE"


def build_multipost_task(
    title: str,
    content: str,
    platform_code: str,
    tags: list[str] | None = None,
    images: list[str] | None = None,
    videos: list[str] | None = None,
) -> dict:
    return {
        "targetClientId": settings.multipost_target_client_id,
        "taskType": "PUBLISH_POST",
        "taskData": {
            "platforms": [{"name": platform_code}],
            "data": {
                "title": title,
                "content": content,
                "images": images or [],
                "videos": videos or [],
                "tags": tags or [],
            },
            "isAutoPublish": settings.multipost_auto_publish,
            "timestamp": int(time.time() * 1000),
        },
    }


def publish_via_multipost(
    title: str,
    content: str,
    platform_label: str,
    tags: list[str] | None = None,
    images: list[str] | None = None,
    videos: list[str] | None = None,
) -> PublishResult:
    platform_code = resolve_platform_code(platform_label)
    payload = build_multipost_task(title, content, platform_code, tags, images, videos)
    if not settings.multipost_api_key or not settings.multipost_target_client_id:
        return PublishResult(
            status="needs_config",
            provider="multipost",
            platform_code=platform_code,
            request_payload=payload,
            error="未配置 MULTIPOST_API_KEY 或 MULTIPOST_TARGET_CLIENT_ID，已创建待配置发布任务，未调用真实平台。",
        )

    base_url = settings.multipost_api_base_url.rstrip("/")
    try:
        with httpx.Client(timeout=settings.ai_request_timeout_seconds) as client:
            response = client.post(
                f"{base_url}/extension/task",
                headers={"Authorization": f"Bearer {settings.multipost_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        # Log full upstream response (may contain task IDs, error details) but
        # only return a sanitized message to the caller — the PublishResult.error
        # field is persisted to the DB and shown in the admin UI, so it must not
        # leak the API URL or raw upstream body.
        logger.error(
            "MultiPost publish upstream error: status=%s body=%s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        return PublishResult(
            status="failed",
            provider="multipost",
            platform_code=platform_code,
            request_payload=payload,
            error=f"MultiPost 返回 HTTP {exc.response.status_code}",
        )
    except Exception as exc:
        # httpx connection errors stringify with the full URL (which embeds the
        # API key in some setups). Only persist the exception type to the DB.
        logger.exception("MultiPost publish failed")
        return PublishResult(
            status="failed",
            provider="multipost",
            platform_code=platform_code,
            request_payload=payload,
            error=f"{type(exc).__name__}",
        )

    task_data = data.get("data") if isinstance(data, dict) else {}
    success = bool(data.get("success")) if isinstance(data, dict) else False
    external_status = str((task_data or {}).get("status") or "").upper()
    status = "pending" if success and external_status in {"", "PENDING", "RUNNING"} else "submitted" if success else "failed"
    return PublishResult(
        status=status,
        provider="multipost",
        platform_code=platform_code,
        external_task_id=str((task_data or {}).get("taskId") or (task_data or {}).get("id") or ""),
        request_payload=payload,
        response_payload=data if isinstance(data, dict) else {"raw": data},
        error="" if success else str(data.get("error") or "MultiPost API 返回 success=false"),
    )
