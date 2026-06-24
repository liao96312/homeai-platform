from fastapi import HTTPException, status

from backend.app.models.domain import User


ROLE_AGENT_MAP = {
    "sales": "sales",
    "sales_director": "sales",
    "designer": "design",
    "design": "design",
    "design_manager": "design",
    "promo": "promo",
    "promo_manager": "promo",
    "management": "management",
}

AGENT_TO_ROLES = {
    "sales": {"sales", "sales_director"},
    "design": {"designer", "design_manager"},
    "promo": {"promo", "promo_manager"},
    "management": {"management"},
}

ROLE_PERMISSION_ALIASES = {
    "sales": {"sales", "sales_director"},
    "designer": {"designer", "design_manager"},
    "design": {"designer", "design_manager"},
    "promo": {"promo", "promo_manager"},
    "management": {"management"},
}

HIDDEN_LEGACY_KB_KEYS = {"salesScript", "cases", "competitor"}
CANONICAL_KB_ORDER = {"product": 0, "design": 1, "promotion": 2, "management": 3, "public": 4}


def row(obj, *fields):
    return {field: getattr(obj, field) for field in fields}


def pagination(limit: int = 50, offset: int = 0, max_limit: int = 100) -> tuple[int, int]:
    return max(1, min(int(limit or 50), max_limit)), max(0, int(offset or 0))


def user_payload(user: User):
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.full_name,
        "role": {"key": user.role.key, "name": user.role.name, "color": user.role.color},
    }


def assert_agent_access(user: User, conversation_key: str | None) -> None:
    if user.role.key == "admin" or not conversation_key:
        return
    allowed = AGENT_TO_ROLES.get(conversation_key)
    if allowed and user.role.key not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权访问该助手")
