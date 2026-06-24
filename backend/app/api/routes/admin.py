
from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db.session import commit_or_rollback, get_db
from backend.app.api.payloads import agent_payload, kb_payload, role_payload
from backend.app.api.schemas import (
    AgentUpdateRequest,
    KnowledgeBaseCreateRequest,
    PermissionUpdateRequest,
    SystemConfigUpdateRequest,
)
from backend.app.api.shared import CANONICAL_KB_ORDER, HIDDEN_LEGACY_KB_KEYS, ROLE_AGENT_MAP, row, user_payload
from backend.app.models.domain import (
    Agent, KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgePermission, OperationLog, Role, SystemConfig, User,
)
from backend.app.services.knowledge_cache import clear_search_cache
from backend.app.services.knowledge_store import delete_kb_collection
from backend.app.api.routes._routers import router
from backend.app.api.routes._helpers import (
    add_log, assert_admin, business_insights_payload, knowledge_hit_rates, weekly_usage_payload,
    clear_config_enabled_cache,
)


@router.get("/admin/bootstrap")
def admin_bootstrap(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    is_admin = user.role.key == "admin"
    role_key = user.role.key
    roles = db.scalars(select(Role).order_by(Role.id)).all()
    role_payloads = [role_payload(db, r) for r in roles]
    visible_role_payloads = [item for item in role_payloads if is_admin or item["key"] == role_key]
    business_role_payloads = [item for item in role_payloads if item["key"] != "admin"]
    kbs = db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id)).all()
    perms = db.scalars(select(KnowledgePermission)).all()

    visible_kb_keys = {p.kb.key for p in perms if is_admin or (p.role.key == role_key and p.can_view)}
    visible_agent_key = ROLE_AGENT_MAP.get(role_key)
    agents_query = select(Agent).order_by(Agent.id)
    if not is_admin and visible_agent_key:
        agents_query = agents_query.where(Agent.key == visible_agent_key)

    total_docs = db.scalar(select(func.count(KnowledgeDocument.id))) or 0
    total_chunks = db.scalar(select(func.count(KnowledgeChunk.id))) or 0
    visible_kbs = [k for k in kbs if k.key in visible_kb_keys and k.key not in HIDDEN_LEGACY_KB_KEYS]
    visible_kbs.sort(key=lambda item: (CANONICAL_KB_ORDER.get(item.key, 100), item.id))
    hit_rates = knowledge_hit_rates(db, [k.key for k in visible_kbs])
    insights = business_insights_payload(db, user)

    return {
        "currentUser": user_payload(user),
        "metrics": [
            {"label": "文档总数", "value": str(total_docs), "trend": f"共{total_chunks}切片", "icon": "📄", "theme": "blue"},
            {"label": "知识库命中", "value": insights["rag"]["hitRate"], "trend": f"{insights['rag']['totalQueries']}次检索", "icon": "📚", "theme": "green"},
            {"label": "线索转化", "value": insights["sales"]["conversionRate"], "trend": f"{insights['sales']['highValueLeads']}条高意向", "icon": "🎯", "theme": "orange"},
            {"label": "Agent 成功率", "value": insights["agent"]["successRate"], "trend": f"{insights['agent']['totalRuns']}次运行", "icon": "🤖", "theme": "purple"},
        ],
        "agents": [agent_payload(db, a) for a in db.scalars(agents_query)],
        "roles": visible_role_payloads,
        "allRoles": role_payloads if is_admin else visible_role_payloads,
        "assignableRoles": business_role_payloads if is_admin else visible_role_payloads,
        "permissionRoles": business_role_payloads if is_admin else visible_role_payloads,
        "knowledgeBases": [kb_payload(db, k, hit_rates) for k in visible_kbs],
        "permissions": [
            {"kbKey": p.kb.key, "roleKey": p.role.key, "view": p.can_view, "edit": p.can_edit, "manage": p.can_manage}
            for p in perms
            if (is_admin or p.role.key == role_key)
            and p.kb.key in visible_kb_keys
            and p.kb.key not in HIDDEN_LEGACY_KB_KEYS
        ],
        "configs": [
            row(c, "key", "name", "description", "enabled")
            for c in db.scalars(select(SystemConfig).order_by(SystemConfig.id))
        ],
        "logs": [
            row(log, "icon", "title", "detail", "time_label", "theme")
            for log in db.scalars(select(OperationLog).order_by(OperationLog.id.desc()).limit(20))
        ],
        "weeklyUsage": weekly_usage_payload(db),
        "businessInsights": insights,
    }


@router.patch("/admin/configs/{config_key}")
def update_system_config(
    config_key: str,
    req: SystemConfigUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_admin(user)
    config = db.scalar(select(SystemConfig).where(SystemConfig.key == config_key))
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")
    config.enabled = req.enabled
    add_log(db, "⚙️", "更新系统配置", f"{config.name} 已{'开启' if req.enabled else '关闭'} · 操作人：{user.full_name}", "orange")
    commit_or_rollback(db)
    clear_config_enabled_cache(config_key)
    db.refresh(config)
    return row(config, "key", "name", "description", "enabled")


@router.patch("/admin/agents/{agent_key}")
def update_agent(
    agent_key: str,
    req: AgentUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_admin(user)
    if req.status not in {"online", "paused", "maintenance"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="状态只能是 online、paused 或 maintenance")
    agent = db.scalar(select(Agent).where(Agent.key == agent_key))
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI助手不存在")
    agent.status = req.status
    add_log(db, "🤖", "切换AI运行状态", f"{agent.name} 切换为 {req.status} · 操作人：{user.full_name}", "blue")
    commit_or_rollback(db)
    db.refresh(agent)
    return row(agent, "key", "name", "icon", "theme", "status", "calls_today", "success_rate", "avg_latency")


@router.patch("/admin/permissions/{kb_key}/{role_key}")
def update_permission(
    kb_key: str,
    role_key: str,
    req: PermissionUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_admin(user)
    kb = db.scalar(select(KnowledgeBase).where(KnowledgeBase.key == kb_key))
    role = db.scalar(select(Role).where(Role.key == role_key))
    if not kb or not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库或角色不存在")
    if req.manage and not req.edit:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理权限必须包含编辑权限")
    if req.edit and not req.view:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="编辑权限必须包含查看权限")
    perm = db.scalar(select(KnowledgePermission).where(KnowledgePermission.kb_id == kb.id, KnowledgePermission.role_id == role.id))
    if not perm:
        perm = KnowledgePermission(kb_id=kb.id, role_id=role.id)
        db.add(perm)
    perm.can_view = req.view
    perm.can_edit = req.edit
    perm.can_manage = req.manage
    add_log(db, "🔐", "修改角色权限", f"{role.name} / {kb.name}：查看={req.view}，编辑={req.edit}，管理={req.manage} · 操作人：{user.full_name}", "purple")
    commit_or_rollback(db)
    db.refresh(perm)
    return {"kbKey": kb.key, "roleKey": role.key, "view": perm.can_view, "edit": perm.can_edit, "manage": perm.can_manage}


@router.post("/admin/knowledge-bases")
def create_knowledge_base(
    req: KnowledgeBaseCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_admin(user)
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="知识库名称不能为空")
    base_key = "".join(ch for ch in clean_name.lower() if ch.isalnum())[:24] or f"kb{len(clean_name)}"
    key = base_key
    suffix = 1
    while db.scalar(select(KnowledgeBase).where(KnowledgeBase.key == key)):
        suffix += 1
        key = f"{base_key}{suffix}"
    kb = KnowledgeBase(key=key, name=clean_name, description=req.description.strip() or "自定义知识库", icon=req.icon[:4] or "📚", theme=req.theme)
    db.add(kb)
    db.flush()
    for role in db.scalars(select(Role)).all():
        db.add(
            KnowledgePermission(
                kb_id=kb.id,
                role_id=role.id,
                can_view=role.key == "admin",
                can_edit=role.key == "admin",
                can_manage=role.key == "admin",
            )
        )
    add_log(db, "📚", "新建知识库", f"{clean_name} 已创建，默认仅管理员可管理 · 操作人：{user.full_name}", "green")
    commit_or_rollback(db)
    db.refresh(kb)
    return kb_payload(db, kb)


@router.delete("/admin/knowledge-bases/{kb_key}")
def delete_knowledge_base(
    kb_key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_admin(user)
    kb = db.scalar(select(KnowledgeBase).where(KnowledgeBase.key == kb_key))
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    if kb.key in CANONICAL_KB_ORDER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统知识库不能删除，请通过权限控制访问范围")

    for chunk in db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb.id)).all():
        db.delete(chunk)
    for doc in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.kb_id == kb.id)).all():
        db.delete(doc)
    for perm in db.scalars(select(KnowledgePermission).where(KnowledgePermission.kb_id == kb.id)).all():
        db.delete(perm)
    db.delete(kb)
    add_log(db, "🗑️", "删除知识库", f"{kb.name} 已删除，文档、切片与权限一并清理 · 操作人：{user.full_name}", "red")
    commit_or_rollback(db)
    clear_search_cache(kb_key)
    delete_kb_collection(kb_key)
    return {"deleted": True, "kbKey": kb_key}


