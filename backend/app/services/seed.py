from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.db.session import commit_or_rollback
from backend.app.models.domain import (
    Agent,
    Conversation,
    DashboardMetric,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePermission,
    MarketingPlatform,
    OperationLog,
    PromoTemplate,
    Role,
    SystemConfig,
    User,
)

DEFAULT_PERMISSIONS = (False, False, False)
DEFAULT_USERS = (
    ("admin", "平台管理员", "admin", "seed_admin_password"),
    ("sales", "销售顾问小王", "sales", "seed_sales_password"),
    ("sales_director", "销售总监张总", "sales_director", "seed_sales_director_password"),
    ("designer", "设计师小林", "designer", "seed_designer_password"),
    ("design_manager", "设计经理周工", "design_manager", "seed_design_manager_password"),
    ("promo", "运营小陈", "promo", "seed_promo_password"),
    ("promo_manager", "推广经理李经理", "promo_manager", "seed_promo_manager_password"),
    ("management", "管理层负责人", "management", "seed_management_password"),
)

ORG_ROLE_SPECS = {
    "admin": ("超级管理员", "#1677FF"),
    "sales": ("销售团队", "#FA8C16"),
    "sales_director": ("销售总监", "#D46B08"),
    "designer": ("设计师", "#722ED1"),
    "design_manager": ("设计经理", "#531DAB"),
    "promo": ("推广团队", "#52C41A"),
    "promo_manager": ("推广经理", "#237804"),
    "management": ("管理层", "#0F766E"),
}

MAIN_KB_SPECS = {
    "product": ("销售库", "产品工艺、报价、话术、FAQ、竞品分析", "💼", "blue"),
    "design": ("设计库", "案例图库、工艺标准、材质规格", "🎨", "purple"),
    "promotion": ("推广库", "品牌规范、竞品分析、爆款文案模板", "📝", "orange"),
    "management": ("管理库", "经营数据、人员绩效、战略资料", "📊", "blue"),
    "public": ("公共库", "公司介绍、规章制度、通用培训资料", "🏢", "green"),
}

KNOWLEDGE_PERMISSION_POLICY = {
    "product": {
        "admin": (1, 1, 1),
        "sales": (1, 1, 0),
        "sales_director": (1, 1, 1),
    },
    "design": {
        "admin": (1, 1, 1),
        "designer": (1, 1, 0),
        "design_manager": (1, 1, 1),
    },
    "promotion": {
        "admin": (1, 1, 1),
        "promo": (1, 1, 0),
        "promo_manager": (1, 1, 1),
    },
    "management": {
        "admin": (1, 1, 1),
        "management": (1, 1, 1),
    },
    "public": {
        "admin": (1, 1, 1),
        "sales": (1, 0, 0),
        "sales_director": (1, 0, 0),
        "designer": (1, 0, 0),
        "design_manager": (1, 0, 0),
        "promo": (1, 0, 0),
        "promo_manager": (1, 0, 0),
        "management": (1, 0, 0),
    },
}

LEGACY_KB_MIGRATION_TARGETS = {
    "salesScript": "product",
    "cases": "design",
    "competitor": "product",
}


def permission_flags(role_key: str, role_perms: dict[str, tuple[int, int, int]]) -> tuple[bool, bool, bool]:
    raw = role_perms.get(role_key, DEFAULT_PERMISSIONS)
    return bool(raw[0]), bool(raw[1]), bool(raw[2])


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Role).limit(1)):
        seed_missing_configs(db)
        sync_knowledge_permission_policy(db)
        migrate_legacy_knowledge_bases(db)
        seed_missing_users(db)
        seed_missing_promo_templates(db)
        if (
            should_repair_demo_copy_on_startup()
            or not db.scalar(select(Agent).limit(1))
            or not db.scalar(select(Conversation).limit(1))
        ):
            repair_demo_copy(db)
        sync_knowledge_permission_policy(db)
        migrate_legacy_knowledge_bases(db)
        return

    roles = [
        Role(key="admin", name="超级管理员", color="#1677FF", user_count=2),
        Role(key="sales", name="销售顾问", color="#FA8C16", user_count=18),
        Role(key="designer", name="设计师", color="#722ED1", user_count=12),
        Role(key="promo", name="推广运营", color="#52C41A", user_count=5),
    ]
    kbs = [
        KnowledgeBase(key=key, name=name, description=description, icon=icon, theme=theme, docs=0, chunks=0, hit_rate="0%", updated_at_label="刚刚")
        for key, (name, description, icon, theme) in MAIN_KB_SPECS.items()
    ]
    db.add_all(roles + kbs)
    db.flush()

    by_role = {role.key: role for role in roles}
    by_kb = {kb.key: kb for kb in kbs}

    users = default_user_rows(by_role)
    db.add_all(users)

    perm_map = KNOWLEDGE_PERMISSION_POLICY
    for kb_key, role_perms in perm_map.items():
        for role_key, role in by_role.items():
            can_view, can_edit, can_manage = permission_flags(role_key, role_perms)
            db.add(
                KnowledgePermission(
                    kb_id=by_kb[kb_key].id,
                    role_id=role.id,
                    can_view=can_view,
                    can_edit=can_edit,
                    can_manage=can_manage,
                )
            )

    db.add_all(
        [
            DashboardMetric(label="今日AI调用", value="2,847", trend="+18.6%", icon="⚡", theme="blue"),
            DashboardMetric(label="线索转化率", value="32.8%", trend="+5.2%", icon="🎯", theme="green"),
            DashboardMetric(label="知识库命中", value="91.4%", trend="+2.1%", icon="📚", theme="orange"),
            DashboardMetric(label="待处理告警", value="7", trend="-3", icon="🔔", theme="purple"),
            Agent(key="sales", name="销售AI助手 · 销售顾问", icon="🤖", theme="blue", status="online", calls_today=0, success_rate="0%", avg_latency="0s"),
            Agent(key="design", name="设计AI助手 · 方案顾问", icon="🎨", theme="orange", status="online", calls_today=0, success_rate="0%", avg_latency="0s"),
            Agent(key="promo", name="推广AI助手 · 内容增长", icon="✨", theme="purple", status="online", calls_today=0, success_rate="0%", avg_latency="0s"),
            Agent(key="management", name="管理AI助手 · 经营参谋", icon="📊", theme="green", status="online", calls_today=0, success_rate="0%", avg_latency="0s"),
            OperationLog(icon="🔐", title="修改设计师角色权限", detail="新增：产品知识库「查看」权限 · 操作人：管理员", time_label="今天 10:32", theme="purple"),
            OperationLog(icon="📚", title="同步产品知识库", detail="新增 24 篇文档，更新 126 个切片", time_label="今天 09:18", theme="blue"),
            OperationLog(icon="⚙️", title="切换默认模型", detail="销售AI助手切换到 DeepSeek 默认模型配置", time_label="昨天 16:20", theme="orange"),
        ]
    )

    db.add_all(
        [
            Conversation(
                key="sales",
                name="销售AI助手 · 销售顾问",
                assistant_name="销售AI · 销售顾问",
                icon="🤖",
                theme="sales",
                preview="[AI] 客户李总询价120平新中式，已生成报价方案",
                time_label="10:32",
                unread=3,
                quick_actions=["客户意向分析", "生成报价", "异议处理", "推荐产品"],
                messages=[
                    {"sender": "ai", "type": "text", "content": "我是销售AI销售顾问，可以帮你做客户意向分析、报价方案和跟进话术。"},
                    {"sender": "me", "type": "text", "content": "客户李总询价120平新中式，预算20万左右"},
                    {"sender": "ai", "type": "card", "title": "客户意向分析", "rows": [["意向评分", "72分"], ["推荐动作", "48小时内邀约到店"], ["报价区间", "18.8万-23.6万"]]},
                ],
            ),
            Conversation(
                key="design",
                name="设计AI助手 · 方案顾问",
                assistant_name="设计AI · 方案顾问",
                icon="🎨",
                theme="design",
                preview="[AI] 已为您生成3套户型方案，请查看",
                time_label="09:15",
                unread=1,
                quick_actions=["分析户型", "生成风格", "材料清单", "效果图建议"],
                messages=[
                    {"sender": "ai", "type": "text", "content": "我是设计AI方案顾问，可以分析户型、推荐风格、生成材料清单。"},
                    {"sender": "me", "type": "text", "content": "想做新中式，客餐厅要显大"},
                    {"sender": "ai", "type": "design", "title": "新中式客餐厅方案", "subtitle": "陶土棕 + 云雾灰 + 铜色五金"},
                ],
            ),
            Conversation(
                key="promo",
                name="推广AI助手 · 内容增长",
                assistant_name="推广AI · 内容增长",
                icon="✨",
                theme="promo",
                preview="[AI] 小红书爆款文案已生成，点击一键发布",
                time_label="昨天",
                unread=0,
                quick_actions=["生成小红书文案", "生成抖音脚本", "朋友圈文案", "活动海报文案"],
                messages=[
                    {"sender": "ai", "type": "text", "content": "我是推广AI内容增长，可以一键生成小红书、抖音、朋友圈和活动文案。"},
                    {"sender": "me", "type": "text", "content": "帮我写个小红书，主题是新中式全屋定制，突出环保材质"},
                    {"sender": "ai", "type": "copy", "platform": "📕 小红书", "title": "🏮 住了3个月，才明白选新中式全屋的正确打开方式", "body": "装修前我以为新中式=贵+老气\n装完才发现，是我肤浅了！\n\n✅ 0甲醛|E0级板材，孩子摸完不过敏\n✅ 燕尾榫工艺，20年不松动\n✅ 整屋收纳设计，东西再多也不乱\n\n#新中式装修 #全屋定制 #家装日记"},
                ],
            ),
            Conversation(
                key="management",
                name="管理AI助手 · 经营参谋",
                assistant_name="管理AI · 经营参谋",
                icon="📊",
                theme="management",
                preview="[AI] 可基于管理库回答经营数据、绩效和战略资料问题",
                time_label="刚刚",
                unread=0,
                quick_actions=["经营数据解读", "绩效资料查询", "制度资料", "战略资料摘要"],
                messages=[
                    {"sender": "ai", "type": "text", "content": "我是管理AI经营参谋，可以基于管理库和公共库协助查看经营资料、人员绩效和战略信息。"},
                ],
            ),
        ]
    )

    db.add_all(
        [
            MarketingPlatform(label="小红书", icon="📕", theme="#FFF0F0"),
            MarketingPlatform(label="抖音", icon="🎬", theme="#F0F0FF"),
            MarketingPlatform(label="朋友圈", icon="📢", theme="#F0FFF4"),
            MarketingPlatform(label="公众号", icon="🌐", theme="#F5F5FF"),
        ]
    )
    db.add_all(
        [
            SystemConfig(key="kb_auto_sync", name="知识库自动同步", description="上传文档后自动切片、embedding 并更新知识库统计", enabled=True),
            SystemConfig(key="chat_archive", name="聊天记录归档", description="保留 AI 对话记录，支持后续质检和复盘", enabled=True),
            SystemConfig(key="ai_safety_review", name="AI安全审核", description="对模型回复进行基础风险检查后再展示", enabled=True),
            SystemConfig(key="manual_publish_confirm", name="发布前人工确认", description="推广内容发布前必须由人工确认", enabled=False),
        ]
    )
    commit_or_rollback(db)
    seed_missing_promo_templates(db)
    if should_repair_demo_copy_on_startup():
        repair_demo_copy(db)
    sync_knowledge_permission_policy(db)
    migrate_legacy_knowledge_bases(db)


def should_repair_demo_copy_on_startup() -> bool:
    return settings.seed_repair_on_startup or settings.app_env.lower() in {"development", "dev", "local"}


def seed_password(password_attr: str) -> str:
    password = str(getattr(settings, password_attr, "") or "").strip()
    if not password:
        env_name = password_attr.upper()
        raise RuntimeError(f"{env_name} must be configured before seeding default users")
    return password


def default_user_rows(roles: dict[str, Role], specs=DEFAULT_USERS) -> list[User]:
    rows = []
    for username, full_name, role_key, password_attr in specs:
        role = roles.get(role_key)
        if not role:
            continue
        rows.append(
            User(
                username=username,
                full_name=full_name,
                role_id=role.id,
                hashed_password=hash_password(seed_password(password_attr)),
            )
        )
    return rows


def seed_missing_users(db: Session) -> None:
    roles = {role.key: role for role in db.scalars(select(Role)).all()}
    existing = set(db.scalars(select(User.username)).all())
    missing_specs = [spec for spec in DEFAULT_USERS if spec[0] not in existing]
    missing = default_user_rows(roles, missing_specs)
    if missing:
        db.add_all(missing)
        commit_or_rollback(db)


def sync_knowledge_permission_policy(db: Session) -> None:
    """Apply the requested role-based knowledge permission matrix."""
    changed = False

    roles = {role.key: role for role in db.scalars(select(Role)).all()}
    for key, (name, color) in ORG_ROLE_SPECS.items():
        role = roles.get(key)
        if not role:
            role = Role(key=key, name=name, color=color, user_count=0)
            db.add(role)
            db.flush()
            roles[key] = role
            changed = True
        elif (role.name, role.color) != (name, color):
            role.name = name
            role.color = color
            changed = True

    kbs = {kb.key: kb for kb in db.scalars(select(KnowledgeBase)).all()}
    for key, (name, description, icon, theme) in MAIN_KB_SPECS.items():
        kb = kbs.get(key)
        if not kb:
            kb = KnowledgeBase(
                key=key,
                name=name,
                description=description,
                icon=icon,
                theme=theme,
                docs=0,
                chunks=0,
                hit_rate="0%",
                updated_at_label="刚刚",
            )
            db.add(kb)
            db.flush()
            kbs[key] = kb
            changed = True
        elif (kb.name, kb.description, kb.icon, kb.theme) != (name, description, icon, theme):
            kb.name = name
            kb.description = description
            kb.icon = icon
            kb.theme = theme
            changed = True

    for kb_key, kb in kbs.items():
        if kb_key not in KNOWLEDGE_PERMISSION_POLICY:
            continue
        policy = KNOWLEDGE_PERMISSION_POLICY[kb_key]
        for role_key, role in roles.items():
            can_view, can_edit, can_manage = permission_flags(role_key, policy)
            perm = db.scalar(
                select(KnowledgePermission).where(
                    KnowledgePermission.kb_id == kb.id,
                    KnowledgePermission.role_id == role.id,
                )
            )
            if not perm:
                db.add(
                    KnowledgePermission(
                        kb_id=kb.id,
                        role_id=role.id,
                        can_view=can_view,
                        can_edit=can_edit,
                        can_manage=can_manage,
                    )
                )
                changed = True
            elif (perm.can_view, perm.can_edit, perm.can_manage) != (can_view, can_edit, can_manage):
                perm.can_view = can_view
                perm.can_edit = can_edit
                perm.can_manage = can_manage
                changed = True

    if changed:
        commit_or_rollback(db)


def migrate_legacy_knowledge_bases(db: Session) -> None:
    """Move old prototype knowledge bases into the five canonical business libraries."""
    changed = False
    for legacy_key, target_key in LEGACY_KB_MIGRATION_TARGETS.items():
        legacy = db.scalar(select(KnowledgeBase).where(KnowledgeBase.key == legacy_key))
        target = db.scalar(select(KnowledgeBase).where(KnowledgeBase.key == target_key))
        if not legacy or not target:
            continue

        for doc in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.kb_id == legacy.id)).all():
            metadata = dict(doc.metadata_json or {})
            metadata.setdefault("legacyKbKey", legacy.key)
            metadata.setdefault("legacyKbName", legacy.name)
            doc.metadata_json = metadata
            doc.kb_id = target.id
            changed = True

        for chunk in db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == legacy.id)).all():
            metadata = dict(chunk.metadata_json or {})
            metadata.setdefault("legacyKbKey", legacy.key)
            metadata.setdefault("legacyKbName", legacy.name)
            chunk.metadata_json = metadata
            chunk.kb_id = target.id
            changed = True

        db.execute(delete(KnowledgePermission).where(KnowledgePermission.kb_id == legacy.id))
        db.delete(legacy)
        changed = True

    if changed:
        for kb in db.scalars(select(KnowledgeBase)).all():
            kb.docs = db.scalar(select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.kb_id == kb.id)) or 0
            kb.chunks = db.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.kb_id == kb.id)) or 0
        commit_or_rollback(db)


def seed_missing_knowledge_bases(db: Session) -> None:
    """Compatibility wrapper for older startup code."""
    sync_knowledge_permission_policy(db)
    migrate_legacy_knowledge_bases(db)


def default_promo_template_rows() -> list[PromoTemplate]:
    return [
        PromoTemplate(
            name="Rednote product seeding",
            platform="小红书",
            scene="product_seeding",
            prompt="Write a first-person home renovation note with pain point, product proof, scenario detail, and soft CTA. Avoid fake prices and exaggerated claims.",
            default_audience="准备装修、关注环保和收纳的家庭客户",
            default_tone="真实、有生活感、有转化力",
            default_selling_points=["ENF环保板材", "全屋收纳规划", "设计师一对一方案"],
            owner_id=None,
        ),
        PromoTemplate(
            name="Douyin short video script",
            platform="抖音",
            scene="short_video",
            prompt="Output a 30-60 second short video script with opening hook, scene list, narration, subtitle bullets, and closing CTA.",
            default_audience="近期准备量房或对比全屋定制品牌的客户",
            default_tone="直接、节奏快、突出对比",
            default_selling_points=["真实案例", "环保材料", "预算可控"],
            owner_id=None,
        ),
        PromoTemplate(
            name="WeChat moment campaign",
            platform="朋友圈",
            scene="campaign",
            prompt="Write a warm WeChat moment campaign post with trust proof, limited action, and consultation invitation. Keep it concise.",
            default_audience="本地装修业主和老客户转介绍人群",
            default_tone="自然、可信、像门店顾问发朋友圈",
            default_selling_points=["免费初步方案", "到店/量房预约", "老客户案例"],
            owner_id=None,
        ),
    ]


def seed_missing_promo_templates(db: Session) -> None:
    existing = set(db.scalars(select(PromoTemplate.name)).all())
    missing = [item for item in default_promo_template_rows() if item.name not in existing]
    if missing:
        db.add_all(missing)
        commit_or_rollback(db)


def repair_demo_copy(db: Session) -> None:
    """Keep demo labels readable after older databases seeded with bad encoding."""
    changed = False

    role_labels = {
        "admin": ("超级管理员", "#1677FF"),
        "sales": ("销售顾问", "#FA8C16"),
        "designer": ("设计师", "#722ED1"),
        "promo": ("推广运营", "#52C41A"),
    }
    for role in db.scalars(select(Role)).all():
        label = role_labels.get(role.key)
        if label and (role.name != label[0] or role.color != label[1]):
            role.name, role.color = label
            changed = True

    user_names = {
        "admin": "平台管理员",
        "sales": "销售顾问小王",
        "designer": "设计师小林",
        "promo": "运营小陈",
    }
    for user in db.scalars(select(User)).all():
        name = user_names.get(user.username)
        if name and user.full_name != name:
            user.full_name = name
            changed = True

    kb_specs = {
        **MAIN_KB_SPECS,
    }
    for kb in db.scalars(select(KnowledgeBase)).all():
        spec = kb_specs.get(kb.key)
        if spec and (kb.name, kb.description, kb.icon, kb.theme) != spec:
            kb.name, kb.description, kb.icon, kb.theme = spec
            changed = True

    metric_specs = {
        "今日AI调用": ("今日AI调用", "⚡", "blue"),
        "线索转化率": ("线索转化率", "🎯", "green"),
        "知识库命中": ("知识库命中", "📚", "orange"),
        "待处理告警": ("待处理告警", "🔔", "purple"),
    }
    metrics = db.scalars(select(DashboardMetric).order_by(DashboardMetric.id)).all()
    for metric, spec in zip(metrics, metric_specs.values()):
        if (metric.label, metric.icon, metric.theme) != spec:
            metric.label, metric.icon, metric.theme = spec
            changed = True

    agent_specs = {
        "sales": ("销售AI助手 · 销售顾问", "🤖", "blue"),
        "design": ("设计AI助手 · 方案顾问", "🎨", "orange"),
        "promo": ("推广AI助手 · 内容增长", "✨", "purple"),
        "management": ("管理AI助手 · 经营参谋", "📊", "green"),
    }
    agents = {agent.key: agent for agent in db.scalars(select(Agent)).all()}
    for key, spec in agent_specs.items():
        agent = agents.get(key)
        if not agent:
            name, icon, theme = spec
            db.add(Agent(key=key, name=name, icon=icon, theme=theme, status="online", calls_today=0, success_rate="0%", avg_latency="0s"))
            changed = True
        elif (agent.name, agent.icon, agent.theme) != spec:
            agent.name, agent.icon, agent.theme = spec
            changed = True

    platform_specs = [
        ("小红书", "📕", "#FFF0F0"),
        ("抖音", "🎬", "#F0F0FF"),
        ("朋友圈", "📢", "#F0FFF4"),
        ("公众号", "🌐", "#F5F5FF"),
    ]
    platforms = db.scalars(select(MarketingPlatform).order_by(MarketingPlatform.id)).all()
    for platform, spec in zip(platforms, platform_specs):
        if (platform.label, platform.icon, platform.theme) != spec:
            platform.label, platform.icon, platform.theme = spec
            changed = True

    config_specs = {
        "kb_auto_sync": ("知识库自动同步", "上传文档后自动切片、embedding 并更新知识库统计"),
        "chat_archive": ("聊天记录归档", "保留 AI 对话记录，支持后续质检和复盘"),
        "ai_safety_review": ("AI安全审核", "对模型回复进行基础风险检查后再展示"),
        "manual_publish_confirm": ("发布前人工确认", "推广内容发布前必须由人工确认"),
    }
    for config in db.scalars(select(SystemConfig)).all():
        spec = config_specs.get(config.key)
        if spec and (config.name, config.description) != spec:
            config.name, config.description = spec
            changed = True

    conversations = {
        "sales": ("销售AI助手 · 销售顾问", "销售AI · 销售顾问", "🤖", "我可以帮你做客户意向分析、报价方案和跟进话术。"),
        "design": ("设计AI助手 · 方案顾问", "设计AI · 方案顾问", "🎨", "我可以分析户型、推荐风格、生成材料清单。"),
        "promo": ("推广AI助手 · 内容增长", "推广AI · 内容增长", "✨", "我可以生成小红书、抖音、朋友圈和活动文案。"),
        "management": ("管理AI助手 · 经营参谋", "管理AI · 经营参谋", "📊", "我可以基于管理库和公共库协助查看经营资料、人员绩效和战略信息。"),
    }
    existing_conversations = {conversation.key: conversation for conversation in db.scalars(select(Conversation)).all()}
    for key, spec in conversations.items():
        name, assistant_name, icon, preview = spec
        conversation = existing_conversations.get(key)
        if not conversation:
            db.add(
                Conversation(
                    key=key,
                    name=name,
                    assistant_name=assistant_name,
                    icon=icon,
                    theme=key,
                    preview=preview,
                    time_label="刚刚",
                    unread=0,
                    quick_actions=[],
                    messages=[{"sender": "ai", "type": "text", "content": preview}],
                )
            )
            changed = True
        elif (conversation.name, conversation.assistant_name, conversation.icon, conversation.preview) != spec:
            conversation.name = name
            conversation.assistant_name = assistant_name
            conversation.icon = icon
            conversation.preview = preview
            changed = True

    log_text = "\n".join(
        f"{item.title} {item.detail} {item.time_label}" for item in db.scalars(select(OperationLog).limit(80)).all()
    )
    mojibake_markers = ("\u9359", "\u93c2", "\u942d", "\u7eef", "\u93ba", "\u7481", "\u95bf", "\u7039", "\u9983", "\u923f", "\u9241", "\u923b")
    if any(marker in log_text for marker in mojibake_markers):
        db.execute(delete(OperationLog))
        db.add_all(
            [
                OperationLog(icon="🔐", title="修改角色权限", detail="新增：产品知识库「查看」权限 · 操作人：管理员", time_label="今天 10:32", theme="purple"),
                OperationLog(icon="📚", title="同步产品知识库", detail="新增 24 篇文档，更新 126 个切片", time_label="今天 09:18", theme="blue"),
                OperationLog(icon="⚙️", title="切换默认模型", detail="销售AI助手切换到 DeepSeek 默认模型配置", time_label="昨天 16:20", theme="orange"),
            ]
        )
        changed = True

    if changed:
        commit_or_rollback(db)


def seed_missing_configs(db: Session) -> None:
    configs = [
        ("kb_auto_sync", "知识库自动同步", "上传文档后自动切片、embedding 并更新知识库统计", True),
        ("chat_archive", "聊天记录归档", "保留 AI 对话记录，支持后续质检和复盘", True),
        ("ai_safety_review", "AI安全审核", "对模型回复进行基础风险检查后再展示", True),
        ("manual_publish_confirm", "发布前人工确认", "推广内容发布前必须由人工确认", False),
    ]
    existing = set(db.scalars(select(SystemConfig.key)).all())
    missing = [
        SystemConfig(key=key, name=name, description=description, enabled=enabled)
        for key, name, description, enabled in configs
        if key not in existing
    ]
    if missing:
        db.add_all(missing)
        commit_or_rollback(db)

