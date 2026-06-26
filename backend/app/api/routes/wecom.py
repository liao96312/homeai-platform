from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db.session import get_db
from backend.app.api.schemas import RobotSendRequest, WecomLongConnectionInboundRequest
from backend.app.core.config import settings
from backend.app.models.domain import User
from backend.app.services.wecom import (
    WecomCryptoError, decrypt_callback_body, parse_inbound_payload,
    send_robot_message, verify_url,
)
from backend.app.api.routes._routers import router, wecom_router
from backend.app.api.routes._helpers import assert_admin
from backend.app.api.routes._wecom_helpers import (
    assert_wecom_internal_token, handle_wecom_agent_event,
)


@router.post("/wecom/robot/send")
def send_wecom_robot(req: RobotSendRequest, user: User = Depends(get_current_user)):
    if user.role.key != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")
    return send_robot_message(req.content, msgtype=req.msgtype, mentioned_list=req.mentioned_list)


@router.get("/wecom/long-connection/status")
def wecom_long_connection_status(user: User = Depends(get_current_user)):
    assert_admin(user)
    return {
        "enabled": settings.wecom_long_connection_enabled,
        "configured": bool(settings.wecom_bot_id and settings.wecom_bot_secret),
        "botId": settings.wecom_bot_id,
        "websocketUrl": settings.wecom_long_connection_url,
        "internalTokenConfigured": bool(settings.wecom_internal_token),
        "agentRuntime": "available",
        "inboundEndpoint": "/api/wecom/long-connection/inbound",
    }


@router.post("/wecom/long-connection/inbound")
async def receive_wecom_long_connection_message(
    req: WecomLongConnectionInboundRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    assert_wecom_internal_token(request)
    payload = {
        "msg_type": req.msg_type or "text",
        "content": req.content or "",
        "from_user": req.from_user or "long_connection_user",
        "conversation_id": req.conversation_id or "",
        "message_id": req.message_id or "",
        "raw": req.raw or {},
    }
    result = handle_wecom_agent_event(db, payload, source="long_connection", send_robot=False)
    return {"ok": result["status"] in {"replied", "ignored", "duplicate"}, **result}


@wecom_router.get("/callback", response_class=PlainTextResponse)
def verify_wecom_callback(msg_signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = ""):
    try:
        return verify_url(echostr, msg_signature, timestamp, nonce)
    except WecomCryptoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@wecom_router.post("/callback", response_class=PlainTextResponse)
async def receive_wecom_callback(
    request: Request,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
    db: Session = Depends(get_db),
):
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    try:
        if msg_signature:
            text = decrypt_callback_body(body, msg_signature, timestamp, nonce)
            payload = parse_inbound_payload(text.encode("utf-8"), "xml")
        else:
            payload = parse_inbound_payload(body, content_type)
    except (ValueError, WecomCryptoError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    handle_wecom_agent_event(db, payload, source="callback", send_robot=True)
    return "success"
