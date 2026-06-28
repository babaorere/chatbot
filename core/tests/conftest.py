from __future__ import annotations

import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config.settings import settings


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


@pytest.fixture
def db_session():
    # Use Postgres from configuration instead of sqlite
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(url)
    # Register models in metadata
    from config.database import Base
    from models.category import Category  # noqa: F401
    from models.product import Product  # noqa: F401
    from models.user import User  # noqa: F401
    from models.order import Order  # noqa: F401
    from models.conversation import Conversation  # noqa: F401
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # Ensure pg_trgm extension is enabled on the database used for testing
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        # Seed default 'General' category first
        db.execute(text("INSERT INTO categories (name, slug, is_system) VALUES ('General', 'general', true) ON CONFLICT (name) DO NOTHING;"))
        # Ensure default value of products.category is 'General'
        db.execute(text("ALTER TABLE products ALTER COLUMN category SET DEFAULT 'General';"))
        # Add foreign key constraint if not exists
        check_fk = db.execute(text("SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_category';")).first()
        if not check_fk:
            db.execute(text("UPDATE products SET category = 'General' WHERE category IS NULL;"))
            db.execute(text("""
                ALTER TABLE products 
                ADD CONSTRAINT fk_products_category 
                FOREIGN KEY (category) REFERENCES categories(name) 
                ON DELETE SET DEFAULT ON UPDATE CASCADE;
            """))
        db.commit()
    except Exception:
        db.rollback()

    # Clean up tables before run to avoid conflicts (include categories, preserving General)
    db.execute(text("TRUNCATE TABLE order_items, orders, cart_items, carts, messages, conversations, products, users CASCADE;"))
    db.execute(text("DELETE FROM categories WHERE is_system = false;"))
    db.commit()
    try:
        yield db
    finally:
        # Clean up tables after run
        db.execute(text("TRUNCATE TABLE order_items, orders, cart_items, carts, messages, conversations, products, users CASCADE;"))
        db.execute(text("DELETE FROM categories WHERE is_system = false;"))
        db.commit()
        db.close()
