"""HTTP route package — aggregates all business-domain routers.

Historically this was a single 1901-line routes.py file. It has been split
into domain modules; this package keeps the public surface stable so that
`from backend.app.api.routes import router, openai_router, wecom_router`
continues to work for main.py and tests.
"""
from backend.app.api.routes._routers import openai_router, router, wecom_router  # noqa: F401

# Importing these modules registers their routes onto the routers above.
from backend.app.api.routes import (  # noqa: F401
    admin,
    agent,
    artifacts,
    business,
    chat,
    knowledge,
    publishing,
    video,
    wecom,
)

# Backwards-compatible re-exports for tests.
from backend.app.api.routes._helpers import weekly_usage_payload  # noqa: F401
from backend.app.api.routes._wecom_helpers import is_duplicate_wecom_callback  # noqa: F401
from backend.app.api.payloads import conversation_payload  # noqa: F401
from backend.app.services.business_tools import parse_promo_content  # noqa: F401

__all__ = [
    "openai_router",
    "router",
    "wecom_router",
    "is_duplicate_wecom_callback",
    "weekly_usage_payload",
    "conversation_payload",
    "parse_promo_content",
]
