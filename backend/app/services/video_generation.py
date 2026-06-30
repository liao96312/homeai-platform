from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import unquote, urljoin, urlparse

import httpx
from fastapi import HTTPException, status

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


def money_printer_payload(
    subject: str,
    *,
    script: str = "",
    aspect: str | None = None,
    source: str | None = None,
    clip_duration: int | None = None,
    materials: list[str] | None = None,
) -> dict[str, Any]:
    local_materials = [{"provider": "local", "url": str(item).strip(), "duration": 0} for item in (materials or []) if str(item).strip()]
    return {
        "video_subject": subject.strip()[:500],
        "video_script": script.strip(),
        "video_terms": None,
        "video_aspect": aspect or settings.video_generation_default_aspect,
        "video_concat_mode": "random",
        "video_transition_mode": None,
        "video_clip_duration": clip_duration or settings.video_generation_default_clip_duration,
        "video_count": 1,
        "video_source": "local" if local_materials else source or settings.video_generation_default_source,
        "video_materials": local_materials or None,
        "video_language": "zh-CN",
        "voice_name": settings.video_generation_default_voice,
        "voice_volume": 1.0,
        "voice_rate": 1.0,
        "bgm_type": "random",
        "bgm_volume": 0.2,
        "subtitle_enabled": True,
        "font_size": 60,
        "stroke_color": "#000000",
        "stroke_width": 1.5,
        "n_threads": 2,
        "paragraph_number": 1,
        "video_script_prompt": "",
        "custom_system_prompt": "",
    }


def create_money_printer_video_task(subject: str, *, script: str = "", materials: list[str] | None = None) -> dict[str, Any]:
    if not subject.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频主题不能为空")

    base_url = settings.money_printer_api_base_url.rstrip("/")
    payload = money_printer_payload(subject, script=script, materials=materials)
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{base_url}/videos", json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError as exc:
        hint = settings.money_printer_project_dir or "MoneyPrinterTurbo 项目目录"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MoneyPrinterTurbo 未启动，请先在 {hint} 运行 API 服务：python main.py",
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.error(
            "MoneyPrinterTurbo create_task upstream error: status=%s body=%s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MoneyPrinterTurbo 返回错误：{exc.response.status_code}",
        ) from exc
    except Exception as exc:
        logger.exception("MoneyPrinterTurbo create_task unexpected failure")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"视频生成服务调用失败：{type(exc).__name__}",
        ) from exc

    if data.get("status") not in {200, "200"}:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"视频生成服务返回失败：{data}")

    task_data = data.get("data") or {}
    task_id = task_data.get("task_id") or task_data.get("taskId") or ""
    return {
        "provider": "MoneyPrinterTurbo",
        "taskId": task_id,
        "status": "submitted",
        "apiBase": base_url,
        "request": payload,
        "response": data,
        "statusUrl": f"{base_url}/tasks/{task_id}" if task_id else "",
    }


async def upload_money_printer_video_material(filename: str, content: bytes | BinaryIO) -> dict[str, Any]:
    if isinstance(content, bytes) and not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="素材文件不能为空")
    base_url = settings.money_printer_api_base_url.rstrip("/")
    safe_name = Path(filename or "material.bin").name
    try:
        async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/video_materials",
                files={"file": (safe_name, content, "application/octet-stream")},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MoneyPrinterTurbo 未启动") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MoneyPrinterTurbo 素材上传失败：{exc.response.status_code}") from exc

    if data.get("status") not in {200, "200"}:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MoneyPrinterTurbo 素材上传失败：{data}")
    material_file = str((data.get("data") or {}).get("file") or "").strip()
    if not material_file:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MoneyPrinterTurbo 未返回素材文件名")
    return {"provider": "MoneyPrinterTurbo", "file": material_file, "response": data}


def cleanup_money_printer_video_materials(files: list[str]) -> dict[str, Any]:
    project_dir = str(settings.money_printer_project_dir or "").strip()
    if not project_dir:
        return {"deleted": [], "skipped": files, "reason": "MONEY_PRINTER_PROJECT_DIR 未配置"}

    local_videos_dir = (Path(project_dir) / "storage" / "local_videos").resolve()
    deleted: list[str] = []
    skipped: list[str] = []
    for item in files:
        filename = Path(str(item or "")).name
        if not filename:
            continue
        target = (local_videos_dir / filename).resolve()
        try:
            if os.path.commonpath([str(local_videos_dir), str(target)]) != str(local_videos_dir):
                skipped.append(filename)
                continue
            if target.exists() and target.is_file():
                target.unlink()
                deleted.append(filename)
            else:
                skipped.append(filename)
        except OSError:
            logger.exception("failed to cleanup MoneyPrinterTurbo material: %s", filename)
            skipped.append(filename)
    return {"deleted": deleted, "skipped": skipped}


def money_printer_health() -> dict[str, Any]:
    base_url = settings.money_printer_api_base_url.rstrip("/")
    try:
        with httpx.Client(timeout=3) as client:
            response = client.get(f"{base_url}/video_materials")
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {"ok": False, "provider": "MoneyPrinterTurbo", "apiBase": base_url, "error": type(exc).__name__}
    files = ((data.get("data") or {}).get("files") or []) if isinstance(data, dict) else []
    return {"ok": True, "provider": "MoneyPrinterTurbo", "apiBase": base_url, "localMaterials": len(files)}


def get_money_printer_task(task_id: str) -> dict[str, Any]:
    if not task_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务 ID 不能为空")

    base_url = settings.money_printer_api_base_url.rstrip("/")
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(f"{base_url}/tasks/{task_id}")
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MoneyPrinterTurbo 未启动") from exc
    except httpx.HTTPStatusError as exc:
        logger.error(
            "MoneyPrinterTurbo get_task upstream error: status=%s body=%s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MoneyPrinterTurbo 查询失败：{exc.response.status_code}",
        ) from exc

    return {"provider": "MoneyPrinterTurbo", "taskId": task_id, "response": data}


def money_printer_task_data(task_id: str) -> dict[str, Any]:
    response = get_money_printer_task(task_id)
    data = response.get("response") or {}
    return data.get("data") or {}


def _task_url_to_local_path(task_id: str, url_or_path: str) -> str:
    value = str(url_or_path or "").strip()
    if not value:
        return ""
    project_dir = str(settings.money_printer_project_dir or "").strip()
    if not project_dir:
        logger.warning("MONEY_PRINTER_PROJECT_DIR is not configured; local video paths will not be available")
        return ""
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if "tasks" not in parts:
            return ""
        task_index = parts.index("tasks")
        relative_parts = parts[task_index + 1 :]
        if len(relative_parts) < 2 or relative_parts[0] != task_id:
            return ""
        return str(Path(project_dir) / "storage" / "tasks" / Path(*relative_parts))
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(Path(project_dir) / value)


def _task_url_to_download_url(url_or_path: str) -> str:
    value = str(url_or_path or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return value
    base_url = settings.money_printer_api_base_url.rstrip("/")
    api_root = base_url.rsplit("/api/", 1)[0] if "/api/" in base_url else base_url
    return urljoin(f"{api_root}/", value.lstrip("/"))


def video_delivery_status(task_id: str) -> dict[str, Any]:
    task = money_printer_task_data(task_id)
    state_value = int(task.get("state", 0) or 0)
    progress = int(task.get("progress", 0) or 0)
    video_urls = list(task.get("combined_videos") or task.get("videos") or [])
    files = []
    for url in video_urls:
        local_path = _task_url_to_local_path(task_id, str(url))
        files.append({
            "url": url,
            "downloadUrl": _task_url_to_download_url(str(url)),
            "localPath": local_path,
            "localPathAvailable": bool(local_path),
        })

    completed = state_value == 1 and progress >= 100
    failed = state_value < 0
    ready_files = files if completed else []
    return {
        "provider": "MoneyPrinterTurbo",
        "taskId": task_id,
        "state": state_value,
        "progress": progress,
        "completed": completed,
        "failed": failed,
        "ready": completed and bool(ready_files),
        "files": files,
        "selectedFile": ready_files[0] if ready_files else None,
        "localPathConfigured": bool(str(settings.money_printer_project_dir or "").strip()),
        "raw": task,
    }
