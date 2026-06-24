import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from backend.app.services.embeddings import embed_text_hash
from backend.app.services.knowledge import bm25_rank, build_relevance_evidence, delete_upload_staging_file, index_upload, save_upload_staging_file
from backend.app.services.rag_gate import classify_rag_query, rag_gate_observation


@pytest.fixture(autouse=True)
def stub_rag_llm_gate(monkeypatch):
    def fake_classifier(text: str):
        if "小龙虾" in text or "你是谁" in text:
            return {
                "allowed": False,
                "intent": "smalltalk",
                "reason": "test_smalltalk",
                "domainIntent": False,
                "projectIntent": False,
                "casualIntent": True,
                "matchedSignals": [],
                "classifier": "test",
                "confidence": 0.95,
            }
        if any(term in text for term in ["公司制度", "报销流程", "请假", "考勤制度", "管理制度"]):
            return {
                "allowed": True,
                "intent": "internal_policy",
                "reason": "test_internal_policy",
                "domainIntent": True,
                "projectIntent": False,
                "casualIntent": False,
                "matchedSignals": [],
                "classifier": "test",
                "confidence": 0.95,
            }
        return {
            "allowed": True,
            "intent": "business_knowledge",
            "reason": "test_business",
            "domainIntent": True,
            "projectIntent": False,
            "casualIntent": False,
            "matchedSignals": [],
            "classifier": "test",
            "confidence": 0.9,
        }

    monkeypatch.setattr("backend.app.services.rag_gate.classify_rag_query_with_llm", fake_classifier)


def test_rag_gate_blocks_pure_smalltalk():
    gate = classify_rag_query("你今天吃小龙虾了吗")

    assert gate["allowed"] is False
    assert gate["intent"] == "smalltalk"
    assert gate["quality"]["domainHitRate"] == 0


def test_rag_gate_allows_when_classifier_unavailable(monkeypatch):
    monkeypatch.setattr("backend.app.services.rag_gate.classify_rag_query_with_llm", lambda _text: None)

    gate = classify_rag_query("任何无法分类的问题")

    assert gate["allowed"] is True
    assert gate["classifier"] == "permissive_fallback"
    assert gate["reason"] == "rag_gate_classifier_unavailable_permissive"


def test_rag_gate_observation_is_compact():
    observation = rag_gate_observation(
        {
            "allowed": True,
            "intent": "business_knowledge",
            "reason": "test_business",
            "classifier": "llm",
            "confidence": 0.93,
            "latencyMs": 123.4,
            "cached": False,
            "quality": {"domainHitRate": 1},
        }
    )

    assert observation == {
        "allowed": True,
        "intent": "business_knowledge",
        "reason": "test_business",
        "classifier": "llm",
        "confidence": 0.93,
        "latencyMs": 123.4,
        "cached": False,
    }


def test_rag_gate_allows_multi_signal_business_query():
    gate = classify_rag_query("客户预算25万，120平，新中式全屋定制怎么报价")

    assert gate["allowed"] is True
    assert gate["intent"] == "business_knowledge"


@pytest.mark.parametrize(
    "query",
    [
        "板材环保",
        "产品报价",
        "柜子质量",
        "销售库里产品报价怎么说",
        "客户问价格太贵怎么回复",
        "设计案例有哪些",
        "推广小红书爆款文案模板",
        "知识库上传失败怎么办",
    ],
)
def test_rag_gate_allows_business_queries(query):
    gate = classify_rag_query(query)

    assert gate["allowed"] is True
    assert gate["intent"] == "business_knowledge"


@pytest.mark.parametrize(
    "query",
    [
        "公司制度",
        "报销流程怎么走",
        "今天请假和考勤制度怎么规定",
        "公司考勤制度是什么",
        "请问管理制度里的报销流程",
    ],
)
def test_rag_gate_allows_internal_policy_queries(query):
    gate = classify_rag_query(query)

    assert gate["allowed"] is True
    assert gate["intent"] == "internal_policy"
    assert gate["domainIntent"] is True


def test_relevance_requires_multiple_independent_signals():
    gate = classify_rag_query("客户预算25万，120平，新中式全屋定制怎么报价")
    one_signal_item = {
        "content": "客户预算需要结合面积和板材报价。",
        "bm25Score": 1.2,
        "rerankScore": 0.0,
        "vectorScore": 0.0,
    }
    two_signal_item = {
        "content": "客户预算25万，120平新中式全屋定制，可按板材、五金、收纳方案报价。",
        "bm25Score": 1.2,
        "rerankScore": 0.6,
        "vectorScore": 0.42,
    }

    assert build_relevance_evidence("客户预算25万，120平，新中式全屋定制怎么报价", one_signal_item, gate)["accepted"] is False
    assert build_relevance_evidence("客户预算25万，120平，新中式全屋定制怎么报价", two_signal_item, gate)["accepted"] is True


def test_relevance_accepts_strong_business_term_with_high_bm25():
    gate = classify_rag_query("板材环保")
    item = {
        "content": "板材环保等级包括 E0、ENF 等标准。",
        "bm25Score": 1.1,
        "rerankScore": 0.0,
        "vectorScore": 0.0,
    }

    evidence = build_relevance_evidence("板材环保", item, gate)

    assert evidence["accepted"] is True
    assert evidence["strongExactTerm"] is True
    assert "bm25_strong" in evidence["reasons"]


def test_bm25_rank_scores_matching_chunks():
    chunks = [
        SimpleNamespace(id=1, content="ENF board standard covers environmental grade and custom cabinet materials."),
        SimpleNamespace(id=2, content="daily chat about dinner and unrelated topics."),
    ]

    ranked = bm25_rank("ENF board environmental", chunks)

    assert ranked
    assert ranked[0][0] == 1
    assert ranked[0][1] > 0


def test_hash_embedding_is_stable():
    assert embed_text_hash("客户预算25万，新中式全屋定制") == embed_text_hash("客户预算25万，新中式全屋定制")


def test_index_upload_rejects_empty_text_even_without_auto_index():
    upload = UploadFile(filename="empty.txt", file=BytesIO(b"   \n"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            index_upload(
                SimpleNamespace(),
                SimpleNamespace(id=1),
                SimpleNamespace(id=1),
                upload,
                auto_index=False,
            )
        )

    assert exc.value.status_code == 400


def test_upload_staging_file_is_saved_and_cleaned(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.app.services.knowledge.settings.knowledge_upload_staging_dir", str(tmp_path))

    path = save_upload_staging_file(123, "报价资料.pdf", b"hello")
    staged = tmp_path / "doc_123.pdf"

    assert path == str(staged)
    assert staged.read_bytes() == b"hello"

    delete_upload_staging_file(SimpleNamespace(id=123, metadata_json={"upload_path": path}))

    assert not staged.exists()
