from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.api.routes._wecom_helpers import dispatch_agent_message, is_duplicate_wecom_callback, is_duplicate_wecom_event
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


def test_duplicate_wecom_long_connection_detects_recent_message_id():
    event = SimpleNamespace(
        source="long_connection",
        from_user="u-1",
        content="hello",
        msg_type="text",
        raw_payload={"MsgId": "frame-123"},
        created_at=datetime.now(timezone.utc),
    )
    db = FakeSession([event])

    assert is_duplicate_wecom_event(
        db,
        {"from_user": "u-1", "msg_type": "text", "content": "hello", "message_id": "frame-123", "raw": {"MsgId": "frame-123"}},
        "hello",
        source="long_connection",
    )


def test_duplicate_wecom_event_is_scoped_by_source():
    event = SimpleNamespace(
        source="callback",
        from_user="u-1",
        content="hello",
        msg_type="text",
        raw_payload={"msgid": "same-id"},
        created_at=datetime.now(timezone.utc),
    )
    db = FakeSession([event])

    assert not is_duplicate_wecom_event(
        db,
        {"from_user": "u-1", "msg_type": "text", "content": "hello", "message_id": "same-id", "raw": {"msgid": "same-id"}},
        "hello",
        source="long_connection",
    )


def test_duplicate_wecom_event_falls_back_to_text_when_message_id_missing():
    event = SimpleNamespace(
        source="long_connection",
        from_user="u-1",
        content="hello",
        msg_type="text",
        raw_payload={},
        created_at=datetime.now(timezone.utc),
    )
    db = FakeSession([event])

    assert is_duplicate_wecom_event(
        db,
        {"from_user": "u-1", "msg_type": "text", "content": "hello", "message_id": "", "raw": {}},
        "hello",
        source="long_connection",
    )


def test_wecom_signature_requires_configured_token(monkeypatch):
    monkeypatch.setattr(settings, "wecom_callback_token", "")

    with pytest.raises(WecomCryptoError):
        verify_signature(settings.wecom_callback_token, "sig", "ts", "nonce", "encrypted")


def test_force_video_dispatch_bypasses_intent_classifier(monkeypatch):
    from backend.app.api.routes import video as video_routes

    captured = {}

    def fake_generate_video(req, user, db):
        captured["req"] = req
        return {"taskId": "task-1"}

    monkeypatch.setattr(video_routes, "generate_video", fake_generate_video)
    user = SimpleNamespace(id=1, role=SimpleNamespace(key="promo"))

    result = dispatch_agent_message("随便剪一下", user=user, db=SimpleNamespace(), force_video=True)

    assert result["route"] == "video"
    assert captured["req"].materials == []
    assert captured["req"].script == "随便剪一下"
