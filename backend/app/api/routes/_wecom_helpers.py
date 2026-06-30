import hmac

from backend.app.db.session import commit_or_rollback
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.shared import ROLE_AGENT_MAP
from backend.app.core.config import settings
from backend.app.models.domain import Role, User, WecomWebhookEvent
from backend.app.api.schemas import (
    DesignRequirementRequest,
    LeadScoreRequest,
    PromoCopyRequest,
    VideoGenerationRequest,
)
from backend.app.services.agent_runtime import classify_agent_intent, run_agent
from backend.app.services.chat import ChatCompletionRequest, ChatMessage, create_chat_completion
from backend.app.services.wecom import send_robot_message
from backend.app.api.routes._helpers import assert_agent_online, config_enabled, require_roles


def dispatch_agent_message(
    text: str,
    user: User,
    db: Session,
    user_id: str | None = None,
    video_materials: list[str] | None = None,
    force_video: bool = False,
) -> dict:
    text = text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息不能为空")
    actor_id = user_id or str(user.id)
    intent = classify_agent_intent(text)
    tool = intent.get("tool")
    if tool == "promo_copy":
        require_roles(user, {"promo"})
        from backend.app.api.routes.business import promo_copy
        result = promo_copy(PromoCopyRequest(topic=text), user=user, db=db)
        return {"route": "promo", "tool": "promo_copy", "intent": intent, "result": result}
    if force_video or video_materials or tool == "video_generation":
        require_roles(user, {"promo"})
        from backend.app.api.routes.video import generate_video
        result = generate_video(VideoGenerationRequest(subject=text, script=text, materials=video_materials or []), user=user, db=db)
        return {"route": "video", "tool": "video_generation", "intent": intent, "result": result}
    if tool == "requirement_card":
        require_roles(user, {"designer"})
        from backend.app.api.routes.business import design_requirement_card
        result = design_requirement_card(DesignRequirementRequest(content=text), user=user, db=db)
        return {"route": "design", "tool": "requirement_card", "intent": intent, "result": result}
    if tool == "lead_score":
        require_roles(user, {"sales"})
        from backend.app.api.routes.business import sales_lead_score
        result = sales_lead_score(LeadScoreRequest(content=text), user=user, db=db)
        return {"route": "sales", "tool": "lead_score", "intent": intent, "result": result}

    visible_agent = ROLE_AGENT_MAP.get(user.role.key)
    if user.role.key != "admin" and not visible_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色未绑定 AI 助手")
    visible_agent = visible_agent or settings.wecom_default_conversation_key
    conversation_key = visible_agent if user.role.key != "admin" else settings.wecom_default_conversation_key
    assert_agent_online(db, conversation_key)
    completion = create_chat_completion(
        ChatCompletionRequest(
            model=settings.deepseek_default_model,
            provider="deepseek",
            messages=[ChatMessage(role="user", content=text)],
            metadata={"conversation_key": conversation_key},
        ),
        role_key=user.role.key,
        conversation_key=conversation_key,
        db=db,
        user_id=actor_id,
        save_memory=config_enabled(db, "chat_archive", True),
        safety_review=config_enabled(db, "ai_safety_review", True),
    )
    return {"route": conversation_key, "tool": "chat", "result": completion}


def format_agent_dispatch_reply(dispatch_result: dict) -> str:
    route = dispatch_result.get("route", "")
    tool = dispatch_result.get("tool", "")
    result = dispatch_result.get("result") or {}
    if tool == "lead_score":
        signals = "；".join(result.get("signals") or [])
        actions = "；".join(result.get("nextActions") or [])
        return (
            f"已调用销售 Agent：客户意向 {result.get('score')} 分 / {result.get('grade')} 级。\n"
            f"建议：{result.get('recommendation')}\n"
            f"识别依据：{signals or '暂无'}\n"
            f"下一步：{actions or '继续补充客户信息'}"
        )
    if tool == "requirement_card":
        missing = "、".join(result.get("missingFields") or [])
        todos = "；".join(result.get("designerTodos") or [])
        return (
            "已调用设计 Agent 并生成需求卡。\n"
            f"客户：{result.get('customerName')}；面积：{result.get('area') or '待确认'}；户型：{result.get('houseType')}\n"
            f"风格：{result.get('style')}；预算：{result.get('budget') or '待确认'}；周期：{result.get('timeline')}\n"
            f"设计待办：{todos}\n"
            f"待补信息：{missing or '已基本补齐'}"
        )
    if tool == "promo_copy":
        content = str(result.get("content") or "")
        return f"已调用推广 Agent 生成文案：\n{content[:1800]}"
    if tool == "video_generation":
        task_id = result.get("taskId") or "未返回任务 ID"
        status_text = result.get("status") or "submitted"
        status_url = result.get("statusUrl") or "暂无"
        return f"已调用视频生成 Agent，MoneyPrinterTurbo 任务已提交。\n任务 ID：{task_id}\n状态：{status_text}\n查询地址：{status_url}"
    if tool == "chat":
        choices = result.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "")
    return f"已完成 Agent 调度：{route}/{tool}"


def video_delivery_payload(dispatch_result: dict) -> dict:
    if dispatch_result.get("tool") != "video_generation":
        return {}
    result = dispatch_result.get("result") or {}
    task_id = result.get("taskId")
    if not task_id:
        return {}
    return {
        "taskId": task_id,
        "provider": result.get("provider") or "MoneyPrinterTurbo",
        "statusUrl": result.get("statusUrl") or "",
        "pollIntervalSeconds": settings.video_generation_poll_interval_seconds,
        "pollTimeoutSeconds": settings.video_generation_poll_timeout_seconds,
    }
def get_wecom_agent_user(db: Session) -> User | None:
    return db.scalar(select(User).join(Role).where(Role.key == "admin", User.is_active))


def raw_payload_message_id(raw_payload: dict | None) -> str:
    if not isinstance(raw_payload, dict):
        return ""
    for key in ("MsgId", "MsgID", "msgid", "msg_id", "message_id", "messageId"):
        value = raw_payload.get(key)
        if value:
            return str(value)
    return ""


def is_duplicate_wecom_event(db: Session, payload: dict, user_text: str, *, source: str) -> bool:
    message_id = payload.get("message_id") or raw_payload_message_id(payload.get("raw"))
    from_user = payload.get("from_user", "")
    normalized_source = "callback" if source == "callback" else source
    since = datetime.now(timezone.utc) - timedelta(minutes=10)
    recent_events = db.scalars(
        select(WecomWebhookEvent)
        .where(
            WecomWebhookEvent.source == normalized_source,
            WecomWebhookEvent.from_user == from_user,
            WecomWebhookEvent.created_at >= since,
        )
        .order_by(WecomWebhookEvent.id.desc())
        .limit(50)  # 10分钟内同一用户最多检查最近50条，避免无效查询
    ).all()
    for event in recent_events:
        if getattr(event, "source", normalized_source) != normalized_source:
            continue
        if message_id and raw_payload_message_id(event.raw_payload) == str(message_id):
            return True
        if not message_id and event.content == user_text and event.msg_type == payload.get("msg_type", ""):
            return True
    return False


def is_duplicate_wecom_callback(db: Session, payload: dict, user_text: str) -> bool:
    return is_duplicate_wecom_event(db, payload, user_text, source="callback")


def assert_wecom_internal_token(request: Request) -> None:
    configured_token = (settings.wecom_internal_token or "").strip()
    if not configured_token:
        # Fail closed: if no token is configured, the internal wecom endpoints
        # are disabled entirely. Previously this branch returned without checking,
        # which let anyone trigger agent dispatches (and LLM API spend) without
        # authentication. Configure WECOM_INTERNAL_TOKEN in env (production
        # already enforces this via validate_runtime_settings).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WECOM_INTERNAL_TOKEN 未配置，企微内部接口已禁用",
        )
    provided_token = request.headers.get("x-homeai-wecom-token", "").strip()
    if not provided_token or not hmac.compare_digest(provided_token, configured_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的企微长连接内部令牌")


def handle_wecom_agent_event(db: Session, payload: dict, *, source: str, send_robot: bool) -> dict:
    inbound_conversation_id = payload.get("conversation_id") or ""
    conversation_key = settings.wecom_default_conversation_key
    user_text = payload.get("content") or ""
    force_video = bool(payload.get("force_video"))
    video_materials = payload.get("video_materials") or []
    normalized_source = "callback" if source == "callback" else source
    if is_duplicate_wecom_event(db, payload, user_text, source=normalized_source):
        return {"status": "duplicate", "reply": "", "conversationKey": conversation_key, "run": {}, "dispatch": {}, "robot": {}}

    reply = ""
    robot_result = {}
    dispatch_result = {}
    run_result = {}
    video_delivery = {}
    status_text = "ignored"
    if payload.get("msg_type") == "text" and user_text.strip():
        try:
            agent_user = get_wecom_agent_user(db)
            if not agent_user:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="未找到可用于企微 Agent 调度的系统用户")
            sender_id = payload.get("from_user") or "anonymous"
            run_result = run_agent(
                db,
                user=agent_user,
                text=user_text,
                executor=lambda text, user, db, user_id=None: dispatch_agent_message(
                    text,
                    user,
                    db,
                    user_id,
                    video_materials=video_materials,
                    force_video=force_video,
                ),
                reply_formatter=format_agent_dispatch_reply,
                channel="wecom",
                conversation_id=inbound_conversation_id or sender_id,
                sender_id=sender_id,
                metadata={
                    "source": source,
                    "fromUser": sender_id,
                    "msgType": payload.get("msg_type", ""),
                    "messageId": payload.get("message_id", ""),
                    "forceVideo": force_video,
                    "videoMaterials": video_materials,
                },
                max_attempts=2,
            )
            dispatch_result = (run_result.get("state") or {}).get("result") or {}
            video_delivery = video_delivery_payload(dispatch_result)
            # Store the business route, not the external WeCom chat/user id, so dashboards and RAG logs aggregate with web/API traffic.
            conversation_key = run_result.get("route") or dispatch_result.get("route") or conversation_key
            reply = run_result.get("output") or format_agent_dispatch_reply(dispatch_result)
            if send_robot:
                robot_result = send_robot_message(reply)
            status_text = "replied"
        except HTTPException as exc:
            reply = str(exc.detail)
            status_text = "blocked"
        except Exception as exc:
            reply = f"企微 Agent 调度失败：{type(exc).__name__}"
            status_text = "blocked"

    raw_payload = payload.get("raw", {})
    if isinstance(raw_payload, dict):
        raw_payload = {
            **raw_payload,
            "MsgId": payload.get("message_id") or raw_payload.get("MsgId") or raw_payload.get("msgid") or "",
            "_agent_dispatch": {
                "route": dispatch_result.get("route"),
                "tool": dispatch_result.get("tool"),
                "runId": run_result.get("id"),
                "runKey": run_result.get("runKey"),
                "runStatus": run_result.get("status"),
                "robot": robot_result,
                "videoDelivery": video_delivery,
                "source": source,
                "wecomConversationId": inbound_conversation_id,
            },
        }
    db.add(
        WecomWebhookEvent(
            source=normalized_source,
            msg_type=payload.get("msg_type", ""),
            from_user=payload.get("from_user", ""),
            conversation_key=conversation_key,
            content=user_text,
            reply=reply,
            status=status_text,
            raw_payload=raw_payload,
        )
    )
    commit_or_rollback(db)
    return {
        "status": status_text,
        "reply": reply,
        "conversationKey": conversation_key,
        "run": run_result,
        "dispatch": dispatch_result,
        "videoDelivery": video_delivery,
        "robot": robot_result,
    }

