from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url

_REPO_ENV = dotenv_values(Path(__file__).resolve().parents[2] / ".env")


def _database_url_for_tests() -> str | None:
    explicit_test_url = os.getenv("TEST_DATABASE_URL")
    if explicit_test_url:
        return explicit_test_url

    runtime_url = _REPO_ENV.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    if runtime_url is None:
        return None
    if os.getenv("GITHUB_ACTIONS") == "true":
        return runtime_url

    parsed = make_url(runtime_url)
    database = parsed.database or ""
    if parsed.drivername.startswith("postgresql") and not database.endswith("_test"):
        test_database = f"{database}_test"
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", test_database) is None:
            raise RuntimeError(f"Unsafe test database name: {test_database!r}")
        admin_url = parsed.set(database="postgres")
        test_url = parsed.set(database=test_database)
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :database"),
                    {"database": test_database},
                ).scalar()
                if exists is None:
                    conn.execute(text(f'CREATE DATABASE "{test_database}"'))
        finally:
            engine.dispose()
        return test_url.render_as_string(hide_password=False)

    return runtime_url


_TEST_DATABASE_URL = _database_url_for_tests()
if _TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ.setdefault("OPENROUTER_API_KEY", "dummy_key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")


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
    from app.lifespan import (
        _ensure_postgres_extensions,
        _run_migrations,
        _seed_business_config,
    )
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
        TenantPortalInvite,
        TenantPortalSession,
        TenantPortalUser,
        User,
    )
    from models.category import Category  # noqa: F401

    settings.openrouter_api_key = "dummy_key"
    settings.jwt_secret = "test-jwt-secret"

    with _sync_engine.begin() as conn:
        _ensure_postgres_extensions(conn)

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
            "TRUNCATE TABLE tenant_portal_sessions, tenant_portal_invites, tenant_portal_users, order_items, orders, cart_items, carts, messages, conversations, products, users CASCADE;"
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
                "TRUNCATE TABLE tenant_portal_sessions, tenant_portal_invites, tenant_portal_users, order_items, orders, cart_items, carts, messages, conversations, products, users CASCADE;"
            )
        )
        db.execute(text("DELETE FROM categories WHERE is_system = false;"))
        db.commit()
        db.close()
