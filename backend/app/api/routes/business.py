from datetime import datetime, timezone

import json

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.api.payloads import (
    artifact_payload, design_assignee_payload, promo_template_payload,
)
from backend.app.api.schemas import (
    DesignCardAssignmentRequest, DesignRequirementRequest, LeadScoreRequest,
    PromoCopyRequest, PromoTemplateRequest, TradeFollowupDraftRequest,
    TradeInquiryAnalyzeRequest, TradeQuoteDraftRequest,
)
from backend.app.models.domain import PromoTemplate, Role, User
from backend.app.services.business_tools import (
    build_design_requirement_card, build_promo_prompt, parse_promo_content, score_lead,
)
from backend.app.services.chat import ChatCompletionRequest, ChatMessage, create_chat_completion
from backend.app.services.trade_tools import analyze_trade_inquiry, draft_trade_followup, draft_trade_quote
from backend.app.core.config import settings
from backend.app.api.routes._routers import router
from backend.app.api.routes._helpers import (
    add_log, assert_agent_online, assert_design_workflow_access, config_enabled,
    get_artifact_or_404, get_promo_template_or_404, require_roles, save_artifact,
    validate_artifact_status,
)


@router.post("/sales/lead-score")
def sales_lead_score(req: LeadScoreRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"sales"})
    if not req.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户描述不能为空")
    result = score_lead(req)
    add_log(
        db,
        "🎯",
        "销售客户初筛",
        f"线索评分 {result['score']} / 等级 {result['grade']} · 操作人：{user.full_name}",
        "orange",
    )
    artifact = save_artifact(db, "lead_score", f"销售初筛 · {result['grade']}级 · {result['score']}分", req.content, result, user, "completed")
    commit_or_rollback(db)
    return {**result, "artifactId": artifact.id}


@router.post("/trade/inquiries/analyze")
def trade_inquiry_analyze(req: TradeInquiryAnalyzeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"sales"})
    if not req.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="询盘内容不能为空")
    result = analyze_trade_inquiry(req.content, req.source)
    title_bits = [
        result["extracted"].get("country") or "未知市场",
        result["extracted"].get("product") or "外贸询盘",
        f"{result['intentScore']}分",
    ]
    artifact = save_artifact(db, "trade_inquiry", " · ".join(title_bits)[:160], req.content, result, user, "completed")
    add_log(db, "🌐", "外贸询盘分析", f"{result['intentScore']}分 · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    return {**result, "artifactId": artifact.id}


@router.post("/trade/quotes/draft")
def trade_quote_draft(req: TradeQuoteDraftRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"sales"})
    if not req.product.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="产品/型号不能为空")
    result = draft_trade_quote(req)
    title = f"{result['tradeTerm']} · {result['product']} · {result['currency']} {result['totalAmount'] or '待确认'}"
    artifact = save_artifact(db, "trade_quote", title[:160], json.dumps(req.model_dump(), ensure_ascii=False), result, user, "draft")
    add_log(db, "💵", "外贸报价草稿", f"{result['product']} · 操作人：{user.full_name}", "green")
    commit_or_rollback(db)
    return {**result, "artifactId": artifact.id, "artifactStatus": artifact.status}


@router.post("/trade/followups/draft")
def trade_followup_draft(req: TradeFollowupDraftRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"sales"})
    if not req.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="跟进内容不能为空")
    result = draft_trade_followup(req)
    title = f"{result['channel']} · {result['subject']}"
    artifact = save_artifact(db, "trade_followup", title[:160], req.content, result, user, "draft")
    add_log(db, "✉️", "外贸跟进草稿", f"{result['subject'][:80]} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    return {**result, "artifactId": artifact.id, "artifactStatus": artifact.status}


@router.post("/design/requirement-card")
def design_requirement_card(req: DesignRequirementRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"designer"})
    if not req.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户需求不能为空")
    result = build_design_requirement_card(req)
    artifact = save_artifact(db, "design_card", f"设计需求卡 · {result['customerName']}", req.content, result, user, "draft")
    add_log(db, "🎨", "生成设计需求卡", f"{result['customerName']} · 操作人：{user.full_name}", "purple")
    commit_or_rollback(db)
    return {**result, "artifactId": artifact.id}


@router.get("/design/assignees")
def list_design_assignees(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_design_workflow_access(user)
    users = db.scalars(
        select(User)
        .join(Role)
        .where(User.is_active, Role.key.in_(["designer", "design_manager"]))
        .order_by(Role.key.desc(), User.id.asc())
    ).all()
    return {"assignees": [design_assignee_payload(item) for item in users]}


@router.patch("/design/requirement-cards/{artifact_id}/assignment")
def assign_design_requirement_card(
    artifact_id: int,
    req: DesignCardAssignmentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_design_workflow_access(user)
    artifact = get_artifact_or_404(db, artifact_id, user)
    if artifact.artifact_type != "design_card":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该业务产物不是设计需求卡")
    if user.role.key not in {"admin", "design_manager"} and artifact.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有管理员、设计经理或创建人可以分配需求卡")

    assigned_user = None
    if req.designer_id:
        assigned_user = db.scalar(
            select(User)
            .join(Role)
            .where(User.id == req.designer_id, User.is_active, Role.key.in_(["designer", "design_manager"]))
        )
        if not assigned_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设计师不存在或已停用")

    result = dict(artifact.result_json or {})
    assignment_status = validate_artifact_status(req.status if assigned_user else "confirmed")
    result["assignment"] = {
        "assignedDesignerId": assigned_user.id if assigned_user else None,
        "assignedDesignerName": assigned_user.full_name if assigned_user else "",
        "assignedById": user.id,
        "assignedByName": user.full_name,
        "assignedAt": datetime.now(timezone.utc).isoformat(),
        "notes": req.notes.strip(),
        "status": assignment_status,
    }
    artifact.result_json = result
    artifact.status = assignment_status
    add_log(
        db,
        "🎨",
        "分配设计需求卡" if assigned_user else "取消设计需求卡分配",
        f"{artifact.title} -> {assigned_user.full_name if assigned_user else '未分配'} · 操作人：{user.full_name}",
        "orange",
    )
    commit_or_rollback(db)
    db.refresh(artifact)
    return artifact_payload(artifact)


@router.get("/promo/templates")
def list_promo_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    query = select(PromoTemplate).where(PromoTemplate.is_active == True)  # noqa: E712
    if user.role.key != "admin":
        query = query.where((PromoTemplate.owner_id == None) | (PromoTemplate.owner_id == user.id))  # noqa: E711
    templates = db.scalars(query.order_by(PromoTemplate.id.desc())).all()
    return {"templates": [promo_template_payload(item) for item in templates]}


@router.post("/promo/templates")
def create_promo_template(req: PromoTemplateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    if not req.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模板名称不能为空")
    template = PromoTemplate(
        name=req.name.strip()[:120],
        platform=req.platform.strip()[:40] or "小红书",
        scene=req.scene.strip()[:80],
        prompt=req.prompt.strip(),
        default_audience=req.default_audience.strip()[:160],
        default_tone=req.default_tone.strip()[:160],
        default_selling_points=[item for item in req.default_selling_points if str(item).strip()],
        is_active=req.is_active,
        owner_id=user.id,
    )
    db.add(template)
    add_log(db, "🧩", "创建推广模板", f"{template.name} / {template.platform} · 操作人：{user.full_name}", "purple")
    commit_or_rollback(db)
    db.refresh(template)
    return promo_template_payload(template)


@router.patch("/promo/templates/{template_id}")
def update_promo_template(template_id: int, req: PromoTemplateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    template = get_promo_template_or_404(db, template_id, user)
    if not req.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模板名称不能为空")
    template.name = req.name.strip()[:120]
    template.platform = req.platform.strip()[:40] or template.platform
    template.scene = req.scene.strip()[:80]
    template.prompt = req.prompt.strip()
    template.default_audience = req.default_audience.strip()[:160]
    template.default_tone = req.default_tone.strip()[:160]
    template.default_selling_points = [item for item in req.default_selling_points if str(item).strip()]
    template.is_active = req.is_active
    add_log(db, "🧩", "更新推广模板", f"{template.name} / {template.platform} · 操作人：{user.full_name}", "purple")
    commit_or_rollback(db)
    db.refresh(template)
    return promo_template_payload(template)


@router.delete("/promo/templates/{template_id}")
def delete_promo_template(template_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    template = get_promo_template_or_404(db, template_id, user)
    template.is_active = False
    add_log(db, "🧩", "停用推广模板", f"{template.name} / {template.platform} · 操作人：{user.full_name}", "orange")
    commit_or_rollback(db)
    return {"deleted": True, "templateId": template_id}


@router.post("/promo/copy")
def promo_copy(req: PromoCopyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_roles(user, {"promo"})
    if not req.topic.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="推广主题不能为空")
    assert_agent_online(db, "promo")
    template = get_promo_template_or_404(db, req.template_id, user) if req.template_id else None
    if template:
        if not req.platform.strip():
            req.platform = template.platform
        if not req.audience.strip():
            req.audience = template.default_audience
        if not req.tone.strip():
            req.tone = template.default_tone
        if not req.selling_points:
            req.selling_points = template.default_selling_points or []
    prompt = build_promo_prompt(req, template)
    completion = create_chat_completion(
        ChatCompletionRequest(
            model=settings.deepseek_default_model,
            provider="deepseek",
            messages=[ChatMessage(role="user", content=prompt)],
            metadata={"conversation_key": "promo"},
            temperature=0.8,
        ),
        role_key=user.role.key,
        conversation_key="promo",
        db=db,
        user_id=str(user.id),
        save_memory=config_enabled(db, "chat_archive", True),
        safety_review=config_enabled(db, "ai_safety_review", True),
    )
    content = completion["choices"][0]["message"]["content"]
    preview = parse_promo_content(content, req.topic)
    template_metadata = {"templateId": template.id if template else None, "templateName": template.name if template else ""}
    artifact_result = {"platform": req.platform, "topic": req.topic, "content": content, **preview, **template_metadata, "metadata": completion.get("metadata", {})}
    artifact = save_artifact(db, "promo_copy", f"{req.platform} · {req.topic}", prompt, artifact_result, user, "draft")
    add_log(db, "📣", "生成推广文案", f"{req.platform} / {req.topic} · 操作人：{user.full_name}", "green")
    commit_or_rollback(db)
    return {
        "platform": req.platform,
        "topic": req.topic,
        "content": content,
        **preview,
        **template_metadata,
        "artifactId": artifact.id,
        "artifactStatus": artifact.status,
        "openai": completion,
    }


