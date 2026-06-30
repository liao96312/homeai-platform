from pathlib import Path
import os

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent



def _resolve_path(value: str) -> str:
    """Resolve relative paths against the project root."""
    if not value or os.path.isabs(value):
        return value
    # sqlite:///./dev.db -> sqlite:///C:/absolute/path/dev.db
    if value.startswith("sqlite:///./"):
        rel = value[len("sqlite:///./"):]
        return f"sqlite:///{_PROJECT_ROOT / rel}"
    if value.startswith("./") or value.startswith("..") or not value.startswith("/"):
        return str(_PROJECT_ROOT / value)
    return value


class Settings(BaseSettings):
    app_name: str = "HomeAI Transformation Platform"
    app_env: str = "development"
    database_url: str = "sqlite:///./dev.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"]
    cors_methods: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_headers: list[str] = ["Authorization", "Content-Type", "X-Request-Id"]
    jwt_secret_key: str = "local-dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8
    password_pbkdf2_iterations: int = 600_000
    hash_embedding_key: str = ""
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 1800
    db_pool_timeout_seconds: int = 30
    db_startup_retry_attempts: int = 10
    db_startup_retry_delay_seconds: float = 2.0
    api_rate_limit_per_minute: int = 120
    ai_rate_limit_per_minute: int = 30
    redis_url: str = ""
    trusted_proxy_ips: list[str] = []
    auto_migrate_on_startup: bool = True
    expose_api_docs: bool | None = None
    knowledge_search_cache_ttl_seconds: int = 600
    knowledge_max_upload_bytes: int = 100 * 1024 * 1024
    knowledge_async_indexing: bool = True
    knowledge_recover_pending_jobs_on_startup: bool = True
    knowledge_recovery_max_workers: int = 2
    knowledge_upload_staging_dir: str = "./uploads/knowledge"
    slow_request_ms: int = 1500
    max_request_body_bytes: int = 12 * 1024 * 1024
    seed_admin_password: str = ""
    seed_sales_password: str = ""
    seed_sales_director_password: str = ""
    seed_designer_password: str = ""
    seed_design_manager_password: str = ""
    seed_promo_password: str = ""
    seed_promo_manager_password: str = ""
    seed_management_password: str = ""
    seed_repair_on_startup: bool = False
    ai_provider: str = "deepseek"
    ai_request_timeout_seconds: float = 60
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_default_model: str = "deepseek-chat"
    rag_gate_classifier: str = "llm"
    rag_gate_min_confidence: float = 0.55
    rag_gate_cache_ttl_seconds: int = 600
    agent_intent_classifier: str = "auto"
    agent_runtime_required: bool = False
    rag_triad_llm_judge_enabled: bool = False
    embedding_provider: str = "fastembed"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_allow_download: bool = False
    embedding_cache_dir: str = "./models/fastembed"

    @field_validator("database_url", "embedding_cache_dir", "chroma_persist_dir", "knowledge_upload_staging_dir", mode="before")
    @classmethod
    def resolve_relative_paths(cls, v: str) -> str:
        return _resolve_path(v) if isinstance(v, str) else v

    @model_validator(mode="after")
    def default_docs_by_environment(self):
        if self.expose_api_docs is None:
            self.expose_api_docs = self.app_env.lower() not in {"production", "prod", "staging"}
        return self

    hf_endpoint: str = "https://hf-mirror.com"
    chroma_persist_dir: str = "./chroma_data"
    # Wecom
    wecom_callback_token: str = ""
    wecom_encoding_aes_key: str = ""
    wecom_corp_id: str = ""
    wecom_robot_webhook_url: str = ""
    wecom_robot_webhook_key: str = ""
    wecom_default_conversation_key: str = "sales"
    wecom_long_connection_enabled: bool = False
    wecom_bot_id: str = ""
    wecom_bot_secret: str = ""
    wecom_long_connection_url: str = "wss://openws.work.weixin.qq.com"
    wecom_internal_token: str = ""
    # Multi-platform publishing via MultiPost-compatible API
    multipost_api_base_url: str = "https://api.multipost.app"
    multipost_api_key: str = ""
    multipost_target_client_id: str = ""
    multipost_auto_publish: bool = True
    money_printer_api_base_url: str = "http://127.0.0.1:8080/api/v1"
    # Default to empty so the app does not silently assume a Windows-only path
    # (D:\workplace\...) when running in a Linux container. Configure
    # MONEY_PRINTER_PROJECT_DIR explicitly in your env when video generation is used.
    money_printer_project_dir: str = ""
    video_material_max_upload_bytes: int = 300 * 1024 * 1024
    video_generation_default_source: str = "pexels"
    video_generation_default_aspect: str = "9:16"
    video_generation_default_clip_duration: int = 5
    video_generation_default_voice: str = "zh-CN-XiaoxiaoNeural"
    video_generation_poll_interval_seconds: int = 15
    video_generation_poll_timeout_seconds: int = 900

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")


settings = Settings()


def validate_runtime_settings() -> None:
    import logging

    _log = logging.getLogger(__name__)
    _log.info("Project root: %s", _PROJECT_ROOT)
    for key in ("database_url", "embedding_cache_dir", "chroma_persist_dir"):
        val = getattr(settings, key, "")
        if val and not val.startswith("sqlite:///") and not os.path.isabs(val):
            _log.warning("Relative path in %s: %s (resolved to %s)", key, val, _resolve_path(val))

    prod_like = settings.app_env.lower() in {"production", "prod", "staging"}
    configured_fields = settings.model_fields_set
    if prod_like and "jwt_secret_key" not in configured_fields:
        raise RuntimeError("JWT_SECRET_KEY must be configured in production-like environments")
    if prod_like and not settings.redis_url:
        raise RuntimeError("REDIS_URL must be configured in production-like environments for distributed rate limiting and cache")
    if prod_like and "*" in settings.cors_origins:
        raise RuntimeError('CORS_ORIGINS must not contain "*" in production-like environments')
    if prod_like and settings.expose_api_docs:
        raise RuntimeError("EXPOSE_API_DOCS must be false in production-like environments")
    if settings.embedding_provider.lower().strip() == "hash" and not settings.hash_embedding_key:
        raise RuntimeError("HASH_EMBEDDING_KEY must be configured when EMBEDDING_PROVIDER=hash")
    # SQLite is fine for local dev but must not be used in production -it does
    # not handle concurrent writers, has no network access from containers,
    # and the dev.db file is volatile.
    if prod_like and settings.database_url.startswith("sqlite:///"):
        raise RuntimeError(
            "DATABASE_URL must be a network database (e.g. postgresql) in production-like environments, "
            f"got sqlite URL: {settings.database_url}"
        )
    # DeepSeek API key is required whenever DeepSeek is the configured provider.
    if prod_like and settings.ai_provider.lower() in {"deepseek", "openai-compatible", "openai_compatible"}:
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY must be configured when ai_provider is deepseek in production-like environments")
    if settings.agent_runtime_required:
        try:
            from langgraph.graph import END, START, StateGraph  # noqa: F401
        except Exception as exc:
            raise RuntimeError("langgraph must be installed when AGENT_RUNTIME_REQUIRED=true") from exc
    seed_password_fields = {
        "seed_admin_password": settings.seed_admin_password,
        "seed_sales_password": settings.seed_sales_password,
        "seed_sales_director_password": settings.seed_sales_director_password,
        "seed_designer_password": settings.seed_designer_password,
        "seed_design_manager_password": settings.seed_design_manager_password,
        "seed_promo_password": settings.seed_promo_password,
        "seed_promo_manager_password": settings.seed_promo_manager_password,
        "seed_management_password": settings.seed_management_password,
    }
    def insecure_seed_password(value: str) -> bool:
        normalized = (value or "").strip().lower()
        placeholder_prefixes = ("change-me", "local-dev", "replace-me", "your-", "example")
        return (
            not normalized
            or len(normalized) < 12
            or normalized.startswith(placeholder_prefixes)
            or normalized.endswith("123")
            or normalized in {"password", "admin"}
        )

    if prod_like and any(
        field not in configured_fields or insecure_seed_password(password)
        for field, password in seed_password_fields.items()
    ):
        raise RuntimeError("Secure seed user passwords must be configured in production-like environments")
    if prod_like and settings.wecom_long_connection_enabled:
        if not settings.wecom_bot_id or not settings.wecom_bot_secret:
            raise RuntimeError("WECOM_BOT_ID and WECOM_BOT_SECRET must be configured when long connection is enabled")
        if not settings.wecom_internal_token:
            raise RuntimeError("WECOM_INTERNAL_TOKEN must be configured when long connection is enabled")
    # MultiPost publishing requires an API key -otherwise publishing silently 401s.
    if prod_like and settings.multipost_auto_publish and not settings.multipost_api_key:
        raise RuntimeError("MULTIPOST_API_KEY must be configured when multipost_auto_publish is true in production-like environments")
