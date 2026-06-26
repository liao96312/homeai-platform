from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(20))
    user_count: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(256))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[Role] = relationship()


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(240))
    icon: Mapped[str] = mapped_column(String(12))
    theme: Mapped[str] = mapped_column(String(40))
    docs: Mapped[int] = mapped_column(Integer, default=0)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    hit_rate: Mapped[str] = mapped_column(String(20), default="0%")
    updated_at_label: Mapped[str] = mapped_column(String(40), default="")


class KnowledgePermission(Base):
    __tablename__ = "knowledge_permissions"
    __table_args__ = (UniqueConstraint("kb_id", "role_id", name="uq_knowledge_permissions_kb_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    can_view: Mapped[bool] = mapped_column(Boolean, default=False)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage: Mapped[bool] = mapped_column(Boolean, default=False)
    kb: Mapped[KnowledgeBase] = relationship()
    role: Mapped[Role] = relationship()


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="indexed")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    kb: Mapped[KnowledgeBase] = relationship()
    uploader: Mapped[User | None] = relationship()


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str] = mapped_column(String(120), default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    embedding: Mapped[list] = mapped_column(JsonType, default=list)
    metadata_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    kb: Mapped[KnowledgeBase] = relationship()
    document: Mapped[KnowledgeDocument] = relationship()


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('online', 'paused', 'maintenance')", name="ck_agents_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(12))
    theme: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    calls_today: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[str] = mapped_column(String(20), default="0%")
    avg_latency: Mapped[str] = mapped_column(String(20), default="0s")


class DashboardMetric(Base):
    __tablename__ = "dashboard_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(40))
    trend: Mapped[str] = mapped_column(String(40))
    icon: Mapped[str] = mapped_column(String(12))
    theme: Mapped[str] = mapped_column(String(40))


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    icon: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str] = mapped_column(Text)
    time_label: Mapped[str] = mapped_column(String(40))
    theme: Mapped[str] = mapped_column(String(40))


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(240), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    assistant_name: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(12))
    theme: Mapped[str] = mapped_column(String(40))
    preview: Mapped[str] = mapped_column(String(240))
    time_label: Mapped[str] = mapped_column(String(40))
    unread: Mapped[int] = mapped_column(Integer, default=0)
    quick_actions: Mapped[list] = mapped_column(JsonType, default=list)
    messages: Mapped[list] = mapped_column(JsonType, default=list)
    message_rows: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.id",
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender: Mapped[str] = mapped_column(String(20), default="ai", index=True)
    message_type: Mapped[str] = mapped_column(String(20), default="text")
    content: Mapped[str] = mapped_column(Text, default="")
    extra_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="message_rows")


class MarketingPlatform(Base):
    __tablename__ = "marketing_platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(40))
    icon: Mapped[str] = mapped_column(String(12))
    theme: Mapped[str] = mapped_column(String(40))


class PromoTemplate(Base):
    __tablename__ = "promo_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(40), default="小红书", index=True)
    scene: Mapped[str] = mapped_column(String(80), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    default_audience: Mapped[str] = mapped_column(String(160), default="准备装修的家庭客户")
    default_tone: Mapped[str] = mapped_column(String(160), default="专业、真实、有转化力")
    default_selling_points: Mapped[list] = mapped_column(JsonType, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    owner: Mapped[User | None] = relationship()


class BusinessArtifact(Base):
    __tablename__ = "business_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="draft")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at_label: Mapped[str] = mapped_column(String(40), default="刚刚")
    owner: Mapped[User | None] = relationship()


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("business_artifacts.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="multipost")
    platform_label: Mapped[str] = mapped_column(String(80), default="")
    platform_code: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    external_task_id: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(160), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    request_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    response_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at_label: Mapped[str] = mapped_column(String(40), default="刚刚")
    updated_at_label: Mapped[str] = mapped_column(String(40), default="刚刚")
    artifact: Mapped[BusinessArtifact | None] = relationship()
    user: Mapped[User | None] = relationship()


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    channel: Mapped[str] = mapped_column(String(40), default="web", index=True)
    conversation_id: Mapped[str] = mapped_column(String(160), default="", index=True)
    sender_id: Mapped[str] = mapped_column(String(120), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    intent: Mapped[str] = mapped_column(String(80), default="")
    route: Mapped[str] = mapped_column(String(80), default="")
    tool_name: Mapped[str] = mapped_column(String(120), default="")
    input_text: Mapped[str] = mapped_column(Text, default="")
    output_text: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    state_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    user: Mapped[User | None] = relationship()


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="completed")
    detail_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    run: Mapped[AgentRun] = relationship()


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    tool_name: Mapped[str] = mapped_column(String(120), default="", index=True)
    status: Mapped[str] = mapped_column(String(40), default="completed", index=True)
    input_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    output_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    run: Mapped[AgentRun] = relationship()


class AgentHandoff(Base):
    __tablename__ = "agent_handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_json: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    run: Mapped[AgentRun] = relationship()
    assigned_to: Mapped[User | None] = relationship()


class RagQueryLog(Base):
    __tablename__ = "rag_query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_key: Mapped[str] = mapped_column(String(40), default="")
    query: Mapped[str] = mapped_column(Text, default="")
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    injected: Mapped[bool] = mapped_column(Boolean, default=False)
    top_sources: Mapped[list] = mapped_column(JsonType, default=list)
    created_at_label: Mapped[str] = mapped_column(String(40), default="刚刚")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    user: Mapped[User | None] = relationship()


class WecomWebhookEvent(Base):
    __tablename__ = "wecom_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), default="callback")
    msg_type: Mapped[str] = mapped_column(String(40), default="")
    from_user: Mapped[str] = mapped_column(String(120), default="")
    conversation_key: Mapped[str] = mapped_column(String(40), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    reply: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="received")
    raw_payload: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
