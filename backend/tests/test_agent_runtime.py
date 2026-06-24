from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.domain import AgentRun, AgentStep, AgentToolCall, Role, User
from backend.app.core.config import settings
from backend.app.services.agent_runtime import classify_agent_intent, mark_stale_running_runs_failed, run_agent


def test_agent_intent_rules_report_score_not_fake_confidence(monkeypatch):
    monkeypatch.setattr(settings, "agent_intent_classifier", "rules")

    result = classify_agent_intent("客户预算25万，本月量房，想了解报价和环保板材")

    assert result["classifier"] == "rules"
    assert result["tool"] == "lead_score"
    assert 0 < result["score"] <= 1
    assert result["confidence"] == result["score"]
    assert result["reason"].startswith("rule_match:")


def test_agent_intent_no_tool_intent_has_zero_score(monkeypatch):
    monkeypatch.setattr(settings, "agent_intent_classifier", "rules")

    result = classify_agent_intent("今天下午随便聊两句")

    assert result["tool"] == "chat"
    assert result["classifier"] == "rules"
    assert result["score"] == 0
    assert result["confidence"] == 0
    assert result["reason"] == "no_tool_intent"


def test_agent_intent_prefers_design_when_prompt_mentions_copy_and_design_style():
    result = classify_agent_intent("这个文案帮我设计一下风格，做成新中式方案")

    assert result["tool"] == "requirement_card"
    assert result["route"] == "design"


def test_agent_runtime_records_run_steps_and_tool_call():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        role = Role(key="sales", name="销售顾问", color="#FA8C16", user_count=0)
        db.add(role)
        db.flush()
        user = User(username="sales", full_name="销售顾问", role_id=role.id, hashed_password="x")
        db.add(user)
        db.commit()
        db.refresh(user)

        def executor(text, user, db, user_id=None):
            return {"route": "sales", "tool": "lead_score", "result": {"score": 80}}

        def formatter(result):
            return "已完成销售线索分析"

        payload = run_agent(db, user=user, text="客户预算25万，准备量房", executor=executor, reply_formatter=formatter)

        assert payload["status"] == "completed"
        assert payload["route"] == "sales"
        assert payload["conversationId"] == "sales"
        assert payload["toolName"] == "lead_score"
        assert payload["output"] == "已完成销售线索分析"
        assert db.scalar(select(AgentRun).where(AgentRun.id == payload["id"])) is not None
        assert len(db.scalars(select(AgentStep).where(AgentStep.run_id == payload["id"])).all()) >= 2
        assert len(db.scalars(select(AgentToolCall).where(AgentToolCall.run_id == payload["id"])).all()) == 1
    finally:
        db.close()


def test_agent_runtime_records_failed_attempt_before_retry_success():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        role = Role(key="sales", name="销售顾问", color="#FA8C16", user_count=0)
        db.add(role)
        db.flush()
        user = User(username="sales2", full_name="销售顾问", role_id=role.id, hashed_password="x")
        db.add(user)
        db.commit()
        db.refresh(user)

        attempts = {"count": 0}

        def executor(text, user, db, user_id=None):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary failure")
            return {"route": "sales", "tool": "lead_score", "result": {"score": 82}}

        payload = run_agent(
            db,
            user=user,
            text="客户预算30万，准备量房",
            executor=executor,
            reply_formatter=lambda _result: "重试后完成",
            max_attempts=2,
        )

        tool_calls = db.scalars(select(AgentToolCall).where(AgentToolCall.run_id == payload["id"]).order_by(AgentToolCall.id)).all()
        assert payload["status"] == "completed"
        assert attempts["count"] == 2
        assert [item.status for item in tool_calls] == ["failed", "completed"]
        assert "temporary failure" in tool_calls[0].error
    finally:
        db.close()


def test_agent_runtime_recovers_when_executor_rolls_back_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        role = Role(key="sales", name="销售顾问", color="#FA8C16", user_count=0)
        db.add(role)
        db.flush()
        user = User(username="sales3", full_name="销售顾问", role_id=role.id, hashed_password="x")
        db.add(user)
        db.commit()
        db.refresh(user)

        attempts = {"count": 0}

        def executor(text, user, db, user_id=None):
            attempts["count"] += 1
            if attempts["count"] == 1:
                db.add(Role(key="temp-role", name="临时角色", color="#000", user_count=0))
                db.flush()
                db.rollback()
                raise RuntimeError("executor rolled back")
            return {"route": "sales", "tool": "lead_score", "result": {"score": 76}}

        payload = run_agent(
            db,
            user=user,
            text="客户预算20万，准备近期量房",
            executor=executor,
            reply_formatter=lambda _result: "已恢复并完成",
            max_attempts=2,
        )

        tool_calls = db.scalars(select(AgentToolCall).where(AgentToolCall.run_id == payload["id"]).order_by(AgentToolCall.id)).all()
        assert payload["status"] == "completed"
        assert attempts["count"] == 2
        assert [item.status for item in tool_calls] == ["failed", "completed"]
        assert "executor rolled back" in tool_calls[0].error
    finally:
        db.close()


def test_agent_runtime_marks_stale_running_runs_failed():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        role = Role(key="sales", name="销售顾问", color="#FA8C16", user_count=0)
        db.add(role)
        db.flush()
        user = User(username="sales4", full_name="销售顾问", role_id=role.id, hashed_password="x")
        db.add(user)
        db.flush()
        run = AgentRun(
            run_key="run_stale_test",
            channel="web",
            sender_id=str(user.id),
            user_id=user.id,
            status="running",
            input_text="测试",
            state_json={},
            updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(run)
        db.commit()

        count = mark_stale_running_runs_failed(db, older_than_minutes=30)
        db.refresh(run)

        assert count == 1
        assert run.status == "failed"
        assert run.error == "agent_run_timeout"
    finally:
        db.close()


def test_agent_intent_routes_video_generation():
    result = classify_agent_intent("帮我生成一条新中式全屋定制产品宣传短视频，要有字幕和配音")

    assert result["tool"] == "video_generation"
    assert result["route"] == "video"


def test_agent_runtime_routes_video_node_and_review_gate():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        role = Role(key="promo", name="推广", color="#722ED1", user_count=0)
        db.add(role)
        db.flush()
        user = User(username="promo", full_name="推广专员", role_id=role.id, hashed_password="x")
        db.add(user)
        db.commit()
        db.refresh(user)

        def executor(text, user, db, user_id=None):
            return {"route": "video", "tool": "video_generation", "result": {"taskId": "task_demo"}}

        payload = run_agent(
            db,
            user=user,
            text="帮我做一条新中式全屋定制产品宣传短视频",
            executor=executor,
            reply_formatter=lambda _result: "视频任务已提交",
        )

        step_names = [item.name for item in db.scalars(select(AgentStep).where(AgentStep.run_id == payload["id"]).order_by(AgentStep.id)).all()]
        assert payload["route"] == "video"
        assert payload["toolName"] == "video_generation"
        assert "video_agent_execution" in step_names
        assert "human_review_gate" in step_names
    finally:
        db.close()
