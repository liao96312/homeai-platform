from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.domain import Agent, Conversation, Role, User
from backend.app.services.seed import seed_if_empty


def test_seed_recovers_default_users_when_roles_exist_without_users(monkeypatch):
    for field in (
        "seed_admin_password",
        "seed_sales_password",
        "seed_sales_director_password",
        "seed_designer_password",
        "seed_design_manager_password",
        "seed_promo_password",
        "seed_promo_manager_password",
        "seed_management_password",
    ):
        monkeypatch.setattr("backend.app.services.seed.settings." + field, "test-password")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add_all(
            [
                Role(key="admin", name="超级管理员", color="#1677FF", user_count=0),
                Role(key="sales", name="销售顾问", color="#FA8C16", user_count=0),
                Role(key="designer", name="设计师", color="#722ED1", user_count=0),
                Role(key="promo", name="推广运营", color="#52C41A", user_count=0),
            ]
        )
        db.commit()

        seed_if_empty(db)

        usernames = set(db.scalars(select(User.username)).all())
        assert {
            "admin",
            "sales",
            "sales_director",
            "designer",
            "design_manager",
            "promo",
            "promo_manager",
            "management",
        }.issubset(usernames)
        agent_keys = set(db.scalars(select(Agent.key)).all())
        conversation_keys = set(db.scalars(select(Conversation.key)).all())
        assert "management" in agent_keys
        assert "management" in conversation_keys
    finally:
        db.close()
