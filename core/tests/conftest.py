from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import text

_REPO_ENV = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
_TEST_DATABASE_URL = (
    os.getenv("TEST_DATABASE_URL")
    or _REPO_ENV.get("DATABASE_URL")
    or os.getenv("DATABASE_URL")
)
if _TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ.setdefault("OPENROUTER_API_KEY", "dummy_key")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_integration = os.getenv("RUN_INTEGRATION_TESTS") == "1"
    if run_integration:
        return

    skip_integration = pytest.mark.skip(
        reason="integration tests require a running API service; set RUN_INTEGRATION_TESTS=1 to enable them"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database() -> None:
    from app.lifespan import _run_migrations, _seed_business_config
    from config.database import Base, SessionLocal, _sync_engine
    from config.settings import settings

    # Register all models in Base metadata before create_all.
    from models import (  # noqa: F401
        BusinessConfig,
        Cart,
        CartItem,
        Conversation,
        KnowledgeBase,
        Message,
        Order,
        OrderItem,
        Product,
        SystemSetting,
        User,
    )
    from models.category import Category  # noqa: F401

    settings.openrouter_api_key = "dummy_key"

    Base.metadata.create_all(bind=_sync_engine)

    with _sync_engine.begin() as conn:
        _run_migrations(conn)

    with SessionLocal() as db:
        _seed_business_config(db)
        db.commit()


@pytest.fixture
def db_session(initialize_test_database: None):
    from config.database import SessionLocal

    db = SessionLocal()

    # Clean up tables before run to avoid conflicts (include categories, preserving General)
    db.execute(
        text(
            "TRUNCATE TABLE order_items, orders, cart_items, carts, messages, conversations, products, users CASCADE;"
        )
    )
    db.execute(text("DELETE FROM categories WHERE is_system = false;"))
    db.commit()
    try:
        yield db
    finally:
        # Clean up tables after run
        db.execute(
            text(
                "TRUNCATE TABLE order_items, orders, cart_items, carts, messages, conversations, products, users CASCADE;"
            )
        )
        db.execute(text("DELETE FROM categories WHERE is_system = false;"))
        db.commit()
        db.close()
