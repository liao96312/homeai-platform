from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.app.api.routes.publishing import create_publish_jobs
from backend.app.api.schemas import PublishRequest
from backend.app.services.publishing import build_multipost_task


def test_multipost_task_keeps_media_urls():
    task = build_multipost_task(
        "title",
        "content",
        "DYNAMIC_DOUYIN",
        ["tag"],
        images=["https://example.com/a.jpg"],
        videos=["https://example.com/a.mp4"],
    )

    data = task["taskData"]["data"]
    assert data["images"] == ["https://example.com/a.jpg"]
    assert data["videos"] == ["https://example.com/a.mp4"]


def test_publish_route_rejects_scheduled_jobs():
    req = PublishRequest(
        title="title",
        content="content",
        platforms=["小红书"],
        scheduled_at=datetime.now(timezone.utc),
    )

    with pytest.raises(HTTPException) as exc:
        create_publish_jobs(req, user=None, db=None)

    assert exc.value.status_code == 400
    assert "定时发布暂未启用" in exc.value.detail
