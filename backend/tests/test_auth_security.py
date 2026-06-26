from fastapi.testclient import TestClient
from types import SimpleNamespace

from backend.app.api import auth as auth_module
from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.db.session import SessionLocal, commit_or_rollback
from backend.app.main import app, request_client_ip
from backend.app.models.domain import User
from backend.app.services.embeddings import embed_text_hash


def set_test_admin_password(password: str = "change-me-admin") -> None:
    auth_module._login_attempts.clear()
    auth_module._failed_logins.clear()
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "admin").one()
        user.hashed_password = hash_password(password)
        user.is_active = True
        commit_or_rollback(db)


def test_login_sets_httponly_cookie_and_cookie_auth_works():
    with TestClient(app) as client:
        set_test_admin_password()

        login = client.post(
            "/api/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"username": "admin", "password": "change-me-admin"},
        )
        assert login.status_code == 200
        cookie = login.headers.get("set-cookie", "")
        assert "homeai_access_token=" in cookie
        assert "HttpOnly" in cookie

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "admin"


def test_login_rate_limit_is_username_and_ip_specific():
    auth_module._login_attempts.clear()
    auth_module._failed_logins.clear()

    with TestClient(app) as client:
        statuses = []
        for _ in range(auth_module.LOGIN_ATTEMPTS_PER_MINUTE + 1):
            res = client.post(
                "/api/auth/login",
                headers={"Origin": "http://localhost:5173"},
                json={"username": "missing_user_for_rate_limit", "password": "bad"},
            )
            statuses.append(res.status_code)

    assert statuses[-1] == 429


def test_forwarded_for_is_only_trusted_from_configured_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_ips", ["10.0.0.10", "172.28.0.0/16", " 127.0.0.1 "])
    forged = SimpleNamespace(client=SimpleNamespace(host="203.0.113.55"), headers={"x-forwarded-for": "1.2.3.4"})
    proxied = SimpleNamespace(client=SimpleNamespace(host="10.0.0.10"), headers={"x-forwarded-for": "1.2.3.4"})
    proxied_by_cidr = SimpleNamespace(client=SimpleNamespace(host="172.28.0.20"), headers={"x-forwarded-for": "5.6.7.8, 172.28.0.20"})
    invalid_forwarded = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"x-forwarded-for": "not-an-ip"})

    assert request_client_ip(forged) == "203.0.113.55"
    assert request_client_ip(proxied) == "1.2.3.4"
    assert request_client_ip(proxied_by_cidr) == "5.6.7.8"
    assert request_client_ip(invalid_forwarded) == "127.0.0.1"
    assert auth_module._client_ip(forged) == "203.0.113.55"
    assert auth_module._client_ip(proxied) == "1.2.3.4"


def test_hash_embedding_requires_stable_explicit_key(monkeypatch):
    monkeypatch.setattr(settings, "hash_embedding_key", "")
    try:
        embed_text_hash("hello")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert "HASH_EMBEDDING_KEY" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("hash embedding should require HASH_EMBEDDING_KEY")
