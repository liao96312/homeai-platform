from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api.payloads import artifact_payload
from backend.app.api.routes import conversation_payload, parse_promo_content, weekly_usage_payload
from backend.app.api.routes._helpers import validate_artifact_status


def test_parse_promo_content_uses_first_candidate_title_and_body_section():
    content = """### 标题（3选1）
1. 装修不踩雷｜ENF环保板材才是真安全牌
2. 家有孩子，板材就看这一点

### 正文
装修最怕甲醛超标。
选 ENF 板材更安心。

### CTA
私信发送户型图获取报价。

### 标签
#环保板材 #全屋定制

### 发布建议
封面图使用检测报告。
"""

    parsed = parse_promo_content(content, "兜底标题")

    assert parsed["title"] == "装修不踩雷｜ENF环保板材才是真安全牌"
    assert "装修最怕甲醛超标" in parsed["body"]
    assert "封面图使用检测报告" not in parsed["body"]
    assert parsed["tags"] == ["环保板材", "全屋定制"]


class FakeScalars:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeSession:
    def __init__(self, calls):
        self.calls = calls

    def scalars(self, _query):
        return FakeScalars(self.calls.pop(0))


def test_weekly_usage_payload_uses_real_created_at_weekday():
    monday = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)
    tuesday = datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc)
    db = FakeSession([
        [SimpleNamespace(conversation_key="sales", created_at=monday)],
        [SimpleNamespace(conversation_key="promo", created_at=tuesday)],
    ])

    result = weekly_usage_payload(db, now=datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc))

    assert result[0]["sales"] == 1
    assert result[1]["promo"] == 1
    assert result[0]["promo"] == 0


def test_conversation_payload_exposes_persisted_messages():
    conversation = SimpleNamespace(
        key="sales",
        name="销售AI助手",
        assistant_name="销售AI",
        icon="🤖",
        theme="sales",
        preview="最近回复",
        time_label="刚刚",
        unread=0,
        quick_actions=["生成报价"],
        messages=[{"sender": "me", "type": "text", "content": "客户关心环保"}],
    )

    payload = conversation_payload(conversation)

    assert payload["key"] == "sales"
    assert payload["messages"][0]["content"] == "客户关心环保"


def test_artifact_status_is_simplified_for_legacy_values():
    artifact = SimpleNamespace(
        id=1,
        artifact_type="design_card",
        title="Design card",
        status="assigned",
        source="",
        result_json={"assignment": {"status": "assigned", "assignedDesignerName": "Alice"}},
        created_at_label="now",
        owner=SimpleNamespace(full_name="Owner"),
    )

    payload = artifact_payload(artifact)

    assert payload["status"] == "confirmed"
    assert payload["rawStatus"] == "assigned"
    assert payload["assignment"]["status"] == "confirmed"


def test_validate_artifact_status_accepts_only_simple_statuses_and_legacy_aliases():
    assert validate_artifact_status("draft") == "draft"
    assert validate_artifact_status("assigned") == "confirmed"
    assert validate_artifact_status("pending_review") == "confirmed"

    with pytest.raises(HTTPException):
        validate_artifact_status("waiting_human")
