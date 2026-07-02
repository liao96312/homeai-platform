from types import SimpleNamespace

from backend.app.api.routes._wecom_helpers import dispatch_agent_message
from backend.app.api.routes.business import trade_followup_draft, trade_inquiry_analyze, trade_quote_draft
from backend.app.api.schemas import TradeFollowupDraftRequest, TradeInquiryAnalyzeRequest, TradeQuoteDraftRequest
from backend.app.core.config import settings
from backend.app.services.trade_tools import analyze_trade_inquiry, draft_trade_followup, draft_trade_quote


class FakeSession:
    def __init__(self):
        self.items = []

    def add(self, item):
        item.id = 1
        self.items.append(item)

    def commit(self):
        pass

    def rollback(self):
        pass

    def flush(self):
        for index, item in enumerate(self.items, start=1):
            if not getattr(item, "id", None):
                item.id = index

    def refresh(self, item):
        item.id = getattr(item, "id", 1)


def test_analyze_trade_inquiry_extracts_core_fields():
    result = analyze_trade_inquiry(
        "Dear, we are a distributor in Germany. Please quote 500 pcs kitchen cabinet, FOB Shanghai, T/T. Need CE and RoHS.",
        "email",
    )

    assert result["intentScore"] >= 75
    assert result["buyerType"] == "channel_buyer"
    assert result["extracted"]["quantity"] == "500 pcs"
    assert result["extracted"]["country"] == "Germany"
    assert result["extracted"]["tradeTerm"] == "FOB"
    assert "CE" in result["extracted"]["certifications"]


def test_trade_inquiry_route_saves_artifact():
    user = SimpleNamespace(id=1, full_name="Sales", role=SimpleNamespace(key="sales"))
    db = FakeSession()

    result = trade_inquiry_analyze(
        TradeInquiryAnalyzeRequest(content="Please quote 100 pcs wardrobe to USA, CIF, PayPal.", source="manual"),
        user=user,
        db=db,
    )

    assert result["artifactId"] == 1
    assert result["extracted"]["country"] == "United States"
    assert db.items[0].artifact_type == "trade_inquiry"


def test_draft_trade_quote_calculates_amount_and_flags_missing_fields():
    result = draft_trade_quote(
        TradeQuoteDraftRequest(product="Kitchen cabinet", quantity="500 pcs", unit_price=12.5, trade_term="FOB", destination="Hamburg")
    )

    assert result["totalAmount"] == 6250
    assert "Kitchen cabinet" in result["emailDraft"]
    assert any("交期" in item for item in result["riskPoints"])


def test_draft_trade_followup_uses_inquiry_fields():
    result = draft_trade_followup(
        TradeFollowupDraftRequest(
            content="Please quote 500 pcs kitchen cabinet to Germany, FOB Shanghai.",
            channel="whatsapp",
        )
    )

    assert result["channel"] == "whatsapp"
    assert "kitchen cabinet" in result["messageDraft"]
    assert result["extracted"]["country"] == "Germany"


def test_trade_quote_route_saves_artifact():
    user = SimpleNamespace(id=1, full_name="Sales", role=SimpleNamespace(key="sales"))
    db = FakeSession()

    result = trade_quote_draft(
        TradeQuoteDraftRequest(product="Wardrobe", quantity="100 pcs", unit_price=88, destination="USA"),
        user=user,
        db=db,
    )

    assert result["artifactId"] == 1
    assert result["artifactStatus"] == "draft"
    assert db.items[0].artifact_type == "trade_quote"


def test_trade_followup_route_saves_artifact():
    user = SimpleNamespace(id=1, full_name="Sales", role=SimpleNamespace(key="sales"))
    db = FakeSession()

    result = trade_followup_draft(
        TradeFollowupDraftRequest(content="Please quote 100 pcs wardrobe to USA, CIF."),
        user=user,
        db=db,
    )

    assert result["artifactId"] == 1
    assert result["artifactStatus"] == "draft"
    assert db.items[0].artifact_type == "trade_followup"


def test_agent_dispatch_runs_trade_inquiry(monkeypatch):
    monkeypatch.setattr(settings, "agent_intent_classifier", "rules")
    user = SimpleNamespace(id=1, full_name="Sales", role=SimpleNamespace(key="sales"))
    db = FakeSession()

    result = dispatch_agent_message(
        "德国 distributor 发来 RFQ：Please quote 500 pcs kitchen cabinet, FOB Shanghai, T/T.",
        user=user,
        db=db,
    )

    assert result["tool"] == "trade_inquiry"
    assert result["result"]["artifactId"] == 1
    assert db.items[0].artifact_type == "trade_inquiry"


def test_agent_dispatch_runs_trade_quote(monkeypatch):
    monkeypatch.setattr(settings, "agent_intent_classifier", "rules")
    user = SimpleNamespace(id=1, full_name="Sales", role=SimpleNamespace(key="sales"))
    db = FakeSession()

    result = dispatch_agent_message(
        "帮我生成英文报价单 quotation：500 pcs wardrobe, FOB Shanghai, T/T.",
        user=user,
        db=db,
    )

    assert result["tool"] == "trade_quote"
    assert result["result"]["artifactStatus"] == "draft"
    assert db.items[0].artifact_type == "trade_quote"


def test_agent_dispatch_runs_trade_followup(monkeypatch):
    monkeypatch.setattr(settings, "agent_intent_classifier", "rules")
    user = SimpleNamespace(id=1, full_name="Sales", role=SimpleNamespace(key="sales"))
    db = FakeSession()

    result = dispatch_agent_message(
        "帮我写一封外贸跟进邮件，催德国客户确认 500 pcs wardrobe 报价后的规格和交期",
        user=user,
        db=db,
    )

    assert result["tool"] == "trade_followup"
    assert result["result"]["artifactStatus"] == "draft"
    assert db.items[0].artifact_type == "trade_followup"
