from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class RobotSendRequest(BaseModel):
    content: str
    msgtype: str = "text"
    mentioned_list: list[str] | None = None


class WecomLongConnectionInboundRequest(BaseModel):
    msg_type: str = "text"
    content: str = ""
    from_user: str = ""
    conversation_id: str = ""
    message_id: str = ""
    force_video: bool = False
    video_materials: list[str] = Field(default_factory=list)
    raw: dict | None = None


class SystemConfigUpdateRequest(BaseModel):
    enabled: bool


class PermissionUpdateRequest(BaseModel):
    view: bool
    edit: bool
    manage: bool


class AgentUpdateRequest(BaseModel):
    status: str


class ChatRequest(BaseModel):
    conversation_key: str
    message: str
    model: str = "deepseek-chat"


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: str = ""
    icon: str = "📚"
    theme: str = "blue"


class LeadScoreRequest(BaseModel):
    content: str
    budget: float | None = None
    area: float | None = None
    style: str | None = None
    timeline: str | None = None
    city: str | None = None
    phone: str | None = None


class TradeInquiryAnalyzeRequest(BaseModel):
    content: str
    source: str = "manual"


class TradeQuoteDraftRequest(BaseModel):
    product: str
    quantity: str = ""
    currency: str = "USD"
    unit_price: float | None = None
    trade_term: str = "FOB"
    destination: str = ""
    payment_terms: str = "T/T 30% deposit, 70% before shipment"
    lead_time: str = ""
    moq: str = ""
    validity_days: int = 7
    notes: str = ""


class TradeFollowupDraftRequest(BaseModel):
    content: str
    channel: str = "email"
    stage: str = "first_reply"
    tone: str = "professional and concise"


class PromoCopyRequest(BaseModel):
    topic: str
    platform: str = "小红书"
    audience: str = "准备装修的家庭客户"
    selling_points: list[str] = Field(default_factory=list)
    tone: str = "专业、真实、有转化力"
    template_id: int | None = None


class VideoGenerationRequest(BaseModel):
    subject: str
    script: str = ""
    materials: list[str] = Field(default_factory=list)


class WecomVideoMaterialCleanupRequest(BaseModel):
    files: list[str] = Field(default_factory=list)


class PromoTemplateRequest(BaseModel):
    name: str
    platform: str = "小红书"
    scene: str = ""
    prompt: str = ""
    default_audience: str = "准备装修的家庭客户"
    default_tone: str = "专业、真实、有转化力"
    default_selling_points: list[str] = Field(default_factory=list)
    is_active: bool = True


class DesignRequirementRequest(BaseModel):
    content: str
    customer_name: str | None = None
    area: float | None = None
    house_type: str | None = None
    style: str | None = None
    budget: float | None = None
    timeline: str | None = None


class DesignCardAssignmentRequest(BaseModel):
    designer_id: int | None = None
    notes: str = ""
    status: str = "confirmed"


class AgentDispatchRequest(BaseModel):
    message: str


class AgentRunRequest(BaseModel):
    message: str
    channel: str = "web"
    conversation_id: str = ""
    sender_id: str = ""
    metadata: dict | None = None
    max_attempts: int = 1


class AgentRetryRequest(BaseModel):
    max_attempts: int = 1


class AgentCancelRequest(BaseModel):
    reason: str = ""


class AgentHandoffRequest(BaseModel):
    reason: str
    assigned_to_id: int | None = None


class AgentResumeRequest(BaseModel):
    action: str = "responded"
    response: str = ""
    feedback: str = ""


class ArtifactCreateRequest(BaseModel):
    artifact_type: str
    title: str
    source: str = ""
    result: dict = Field(default_factory=dict)
    status: str = "draft"


class ArtifactUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    result: dict | None = None


class PublishRequest(BaseModel):
    artifact_id: int | None = None
    title: str
    content: str
    platforms: list[str]
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    scheduled_at: datetime | None = None


class PublishJobCreateRequest(BaseModel):
    artifact_id: int | None = None
    title: str
    content: str
    platforms: list[str]
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    scheduled_at: datetime | None = None


class PublishJobRetryRequest(BaseModel):
    provider: str | None = None
