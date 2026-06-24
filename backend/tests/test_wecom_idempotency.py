from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.api.routes import is_duplicate_wecom_callback
from backend.app.core.config import settings
from backend.app.services.wecom import WecomCryptoError, normalize_json_payload, verify_signature


class FakeScalars:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeSession:
    def __init__(self, items):
        self.items = items

    def scalars(self, _query):
        return FakeScalars(self.items)


def test_wecom_json_payload_extracts_message_id():
    payload = normalize_json_payload({
        "msgtype": "text",
        "userid": "u-1",
        "msgid": "m-123",
        "text": {"content": "hello"},
    })

    assert payload["message_id"] == "m-123"
    assert payload["from_user"] == "u-1"
    assert payload["content"] == "hello"


def test_duplicate_wecom_callback_detects_recent_message_id():
    event = SimpleNamespace(
        source="callback",
        from_user="u-1",
        content="hello",
        msg_type="text",
        raw_payload={"msgid": "m-123"},
        created_at=datetime.now(timezone.utc),
    )
    db = FakeSession([event])

    assert is_duplicate_wecom_callback(
        db,
        {"from_user": "u-1", "msg_type": "text", "content": "hello", "message_id": "m-123", "raw": {"msgid": "m-123"}},
        "hello",
    )


def test_wecom_signature_requires_configured_token(monkeypatch):
    monkeypatch.setattr(settings, "wecom_callback_token", "")

    with pytest.raises(WecomCryptoError):
        verify_signature(settings.wecom_callback_token, "sig", "ts", "nonce", "encrypted")
