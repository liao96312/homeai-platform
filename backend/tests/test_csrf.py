from fastapi.testclient import TestClient
from types import SimpleNamespace

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.main import request_body_size_limit


def test_state_changing_request_without_origin_or_bearer_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "bad"})

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin_missing"


def test_bearer_api_request_without_origin_skips_csrf_check():
    with TestClient(app) as client:
        response = client.post("/api/agent/dispatch", headers={"Authorization": "Bearer invalid"}, json={"message": "hello"})

    assert response.status_code != 403


def test_allowed_origin_write_request_passes_csrf_check():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"username": "admin", "password": "bad"},
        )

    assert response.status_code != 403


def test_similar_origin_domain_is_rejected():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": "http://localhost:5173.evil.example"},
            json={"username": "admin", "password": "bad"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin_mismatch"


def test_wecom_internal_token_does_not_bypass_browser_origin_check():
    with TestClient(app) as client:
        response = client.post(
            "/api/wecom/long-connection/inbound",
            headers={"Origin": "http://evil.example", "X-HomeAI-Wecom-Token": "anything"},
            json={"msg_type": "text", "content": "hello"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin_mismatch"


def test_oversized_request_body_is_rejected_before_route_handling():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": "http://localhost:5173", "Content-Length": "999999999"},
            content=b"{}",
        )

    assert response.status_code == 413
    assert response.json()["code"] == "request_body_too_large"


def test_wecom_video_material_upload_uses_video_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_request_body_bytes", 12)
    monkeypatch.setattr(settings, "video_material_max_upload_bytes", 300)
    request = SimpleNamespace(method="POST", url=SimpleNamespace(path="/api/wecom/video-materials"))

    assert request_body_size_limit(request) > settings.max_request_body_bytes
