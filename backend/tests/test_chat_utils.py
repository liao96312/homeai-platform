import pytest
import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.core.config import settings
from backend.app.services.chat import (
    ChatCompletionRequest,
    ChatMessage,
    _prepare_chat_completion,
    assert_user_input_safe,
    build_deepseek_payload,
    evaluate_rag_triad_with_llm,
    llm_error_message,
    merge_system_message,
)


def test_merge_system_message_combines_and_deduplicates_system_messages():
    messages = [
        {"role": "system", "content": "原始系统提示"},
        {"role": "user", "content": "你好"},
        {"role": "system", "content": "多余系统提示"},
    ]

    merge_system_message(messages, "RAG 提示")

    assert [item["role"] for item in messages].count("system") == 1
    assert messages[0]["content"] == "原始系统提示\n\nRAG 提示"
    assert messages[1]["role"] == "user"


def test_user_input_safety_blocks_sensitive_request():
    req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="怎么绕过审核限制")])

    with pytest.raises(HTTPException):
        assert_user_input_safe(req)


def test_deepseek_payload_does_not_forward_openai_n_parameter():
    req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="你好")], n=2)

    payload = build_deepseek_payload(req)

    assert "n" not in payload


def test_deepseek_payload_does_not_forward_default_penalties():
    req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="你好")])

    payload = build_deepseek_payload(req)

    assert "presence_penalty" not in payload
    assert "frequency_penalty" not in payload


def test_chat_completion_request_rejects_empty_messages():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(messages=[])


def test_llm_error_message_is_actionable_for_common_failures():
    timeout_status, timeout_message = llm_error_message("deepseek", httpx.TimeoutException("timeout"))
    connect_status, connect_message = llm_error_message("deepseek", httpx.ConnectError("connect failed"))
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.example.test/chat"))
    auth_status, auth_message = llm_error_message("deepseek", httpx.HTTPStatusError("bad auth", request=response.request, response=response))

    assert timeout_status == 504
    assert "超时" in timeout_message
    assert connect_status == 503
    assert "无法连接" in connect_message
    assert auth_status == 502
    assert "API Key" in auth_message


def test_rag_triad_llm_judge_respects_feature_flag(monkeypatch):
    calls = {"count": 0}

    class Provider:
        def available(self):
            calls["count"] += 1
            return True

    monkeypatch.setattr(settings, "rag_triad_llm_judge_enabled", False)
    monkeypatch.setattr("backend.app.services.chat.get_llm_provider", lambda: Provider())

    result = evaluate_rag_triad_with_llm("客户预算怎么报？", "按资料报价", [{"content": "报价资料"}])

    assert result is None
    assert calls["count"] == 0


def test_prepare_chat_completion_reuses_rag_gate(monkeypatch):
    calls = {"classify": 0, "gate_seen": None}

    class Provider:
        name = "deepseek"

        def available(self):
            return True

    def fake_classify(query):
        calls["classify"] += 1
        return {"allowed": True, "intent": "business_knowledge", "reason": "test", "domainIntent": True}

    def fake_retrieve_context(_db, _query, _conversation_key, user_id="", top_k=5, gate=None):
        assert gate == {"allowed": True, "intent": "business_knowledge", "reason": "test", "domainIntent": True}
        calls["gate_seen"] = gate
        return [
            {
                "content": "报价制度资料",
                "score": 0.95,
                "relevance": {"level": "high", "score": 0.95},
            }
        ], "报价制度资料"

    monkeypatch.setattr("backend.app.services.chat.classify_rag_query", fake_classify)
    monkeypatch.setattr("backend.app.services.chat.retrieve_context", fake_retrieve_context)
    monkeypatch.setattr("backend.app.services.chat.get_llm_provider", lambda _provider=None: Provider())

    context = _prepare_chat_completion(
        ChatCompletionRequest(messages=[ChatMessage(role="user", content="公司报价制度是什么？")]),
        conversation_key="sales",
        db=object(),
        user_id="1",
        safety_review=False,
    )

    assert calls["classify"] == 1
    assert calls["gate_seen"]["intent"] == "business_knowledge"
    assert isinstance(context, dict)
