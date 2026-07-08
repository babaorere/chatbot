"""
lifespan — Bootstrap de la aplicación FastAPI.

Extrae la lógica de inicialización/shutdown de main.py.
El orden de inicialización es:
1. DB: tablas
2. Seed de la configuración del negocio (si no existe)
3. Session service (Redis o InMemory)
4. LLM Provider (ADKLLMProvider con session service)
5. Registro en el container DI
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.container import clear_providers, set_llm_provider, set_redis_client
from config.database import Base, SessionLocal, _sync_engine
from config.redis import create_redis_client
from config.settings import settings
from config.value_limits import (
    CART_QUANTITY_MAX,
    CART_QUANTITY_MIN,
    PRODUCT_MARGIN_MAX,
    PRODUCT_MARGIN_MIN,
    PRODUCT_MONEY_MAX,
    PRODUCT_MONEY_MIN,
    PRODUCT_STOCK_MAX,
    PRODUCT_STOCK_MIN,
    PRODUCT_TAX_MAX,
    PRODUCT_TAX_MIN,
)
from controllers.telegram_controller import prime_catalog_cache, prime_human_agent_cache
from infrastructure.llm.adk_provider import ADKLLMProvider
from models import (  # noqa: F401 – registers models in Base
    category as _category_module,
    SystemAdmin,
    TenantPortalInvite,
    TenantPortalSession,
    TenantPortalUser,
)
from repositories.business_config_repository import BusinessConfigRepository
from scripts.seed_general_products import seed_general
from services.session_service_factory import create_session_service

logger = logging.getLogger(__name__)


def _seed_business_config(db: Session) -> None:
    """Crea la configuración del negocio por defecto si no existe."""
    repo = BusinessConfigRepository(db)
    repo.get_config()
    logger.info("Business configuration verified/seeded")


def _ensure_postgres_extensions(conn: object) -> None:
    """Instala extensiones requeridas antes de materializar metadata con tipos custom."""
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent;"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))


def _add_check_constraint_if_missing(
    conn: object,
    *,
    table: str,
    name: str,
    condition: str,
) -> None:
    exists = conn.execute(
        text("SELECT 1 FROM pg_constraint WHERE conname = :name;"),
        {"name": name},
    ).first()
    if exists:
        return

    conn.execute(
        text(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition});")
    )
    logger.info("Added check constraint %s on %s", name, table)


def _run_migrations(conn: object) -> None:
    """Aplica migraciones DDL en caliente sobre la base de datos."""
    # Seed default 'General' category first
    conn.execute(
        text(
            "INSERT INTO categories (name, slug, is_system) VALUES ('General', 'general', true) ON CONFLICT (name) DO NOTHING;"
        )
    )

    # Migrate existing string categories from products table into categories table
    conn.execute(
        text("""
        INSERT INTO categories (name, slug, is_system)
        SELECT DISTINCT category, LOWER(category), false
        FROM products
        WHERE category IS NOT NULL AND category NOT IN (SELECT name FROM categories)
        ON CONFLICT (name) DO NOTHING;
    """)
    )

    # Ensure default value of products.category is 'General'
    conn.execute(
        text("ALTER TABLE products ALTER COLUMN category SET DEFAULT 'General';")
    )

    # Add format column if missing
    check_format = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='products' AND column_name='format';
    """)
    ).first()
    if not check_format:
        conn.execute(text("ALTER TABLE products ADD COLUMN format VARCHAR(100);"))
        logger.info("Added 'format' column to products table")

    # Add human_agent_available column if missing
    check_human = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='business_config' AND column_name='human_agent_available';
    """)
    ).first()
    if not check_human:
        conn.execute(
            text(
                "ALTER TABLE business_config ADD COLUMN human_agent_available BOOLEAN NOT NULL DEFAULT TRUE;"
            )
        )
        logger.info("Added 'human_agent_available' column to business_config table")

    check_promotions = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='business_config' AND column_name='promotions_config';
    """)
    ).first()
    if not check_promotions:
        conn.execute(
            text(
                "ALTER TABLE business_config ADD COLUMN promotions_config JSON NOT NULL DEFAULT '{}'::json;"
            )
        )
        logger.info("Added 'promotions_config' column to business_config table")

    check_best_sellers = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='business_config' AND column_name='best_sellers_config';
    """)
    ).first()
    if not check_best_sellers:
        conn.execute(
            text(
                "ALTER TABLE business_config ADD COLUMN best_sellers_config JSON NOT NULL DEFAULT '{}'::json;"
            )
        )
        logger.info("Added 'best_sellers_config' column to business_config table")

    check_favorites = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='business_config' AND column_name='favorites_config';
    """)
    ).first()
    if not check_favorites:
        conn.execute(
            text(
                "ALTER TABLE business_config ADD COLUMN favorites_config JSON NOT NULL DEFAULT '{}'::json;"
            )
        )
        logger.info("Added 'favorites_config' column to business_config table")

    check_attention = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='business_config' AND column_name='estimated_attention_minutes';
    """)
    ).first()
    if not check_attention:
        conn.execute(
            text(
                "ALTER TABLE business_config ADD COLUMN estimated_attention_minutes INTEGER NOT NULL DEFAULT 30;"
            )
        )
        logger.info(
            "Added 'estimated_attention_minutes' column to business_config table"
        )

    check_confirmed_at = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='orders' AND column_name='confirmed_at';
    """)
    ).first()
    if not check_confirmed_at:
        conn.execute(text("ALTER TABLE orders ADD COLUMN confirmed_at TIMESTAMP NULL;"))
        logger.info("Added 'confirmed_at' column to orders table")

    _add_check_constraint_if_missing(
        conn,
        table="products",
        name="ck_products_price_range",
        condition=(
            "price IS NULL OR "
            f"(price >= {PRODUCT_MONEY_MIN} AND price <= {PRODUCT_MONEY_MAX})"
        ),
    )
    _add_check_constraint_if_missing(
        conn,
        table="products",
        name="ck_products_stock_range",
        condition=f"stock >= {PRODUCT_STOCK_MIN} AND stock <= {PRODUCT_STOCK_MAX}",
    )
    _add_check_constraint_if_missing(
        conn,
        table="products",
        name="ck_products_cost_range",
        condition=(
            "cost IS NULL OR "
            f"(cost >= {PRODUCT_MONEY_MIN} AND cost <= {PRODUCT_MONEY_MAX})"
        ),
    )
    _add_check_constraint_if_missing(
        conn,
        table="products",
        name="ck_products_margin_range",
        condition=(
            "margin IS NULL OR "
            f"(margin >= {PRODUCT_MARGIN_MIN} AND margin <= {PRODUCT_MARGIN_MAX})"
        ),
    )
    _add_check_constraint_if_missing(
        conn,
        table="products",
        name="ck_products_taxes_range",
        condition=(
            "taxes IS NULL OR "
            f"(taxes >= {PRODUCT_TAX_MIN} AND taxes <= {PRODUCT_TAX_MAX})"
        ),
    )
    _add_check_constraint_if_missing(
        conn,
        table="cart_items",
        name="ck_cart_items_quantity_range",
        condition=f"quantity >= {CART_QUANTITY_MIN} AND quantity <= {CART_QUANTITY_MAX}",
    )
    _add_check_constraint_if_missing(
        conn,
        table="orders",
        name="ck_orders_total_amount_non_negative",
        condition="total_amount >= 0",
    )
    _add_check_constraint_if_missing(
        conn,
        table="order_items",
        name="ck_order_items_quantity_range",
        condition=f"quantity >= {CART_QUANTITY_MIN} AND quantity <= {CART_QUANTITY_MAX}",
    )
    _add_check_constraint_if_missing(
        conn,
        table="order_items",
        name="ck_order_items_unit_price_non_negative",
        condition="unit_price >= 0",
    )
    _add_check_constraint_if_missing(
        conn,
        table="order_items",
        name="ck_order_items_total_price_non_negative",
        condition="total_price >= 0",
    )

    # Add is_bot_paused column if missing
    check_paused = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='conversations' AND column_name='is_bot_paused';
    """)
    ).first()
    if not check_paused:
        conn.execute(
            text(
                "ALTER TABLE conversations ADD COLUMN is_bot_paused BOOLEAN NOT NULL DEFAULT FALSE;"
            )
        )
        logger.info("Added 'is_bot_paused' column to conversations table")

    # Add foreign key constraint if not exists
    check_fk = conn.execute(
        text("""
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_category';
    """)
    ).first()
    if not check_fk:
        conn.execute(
            text("UPDATE products SET category = 'General' WHERE category IS NULL;")
        )
        conn.execute(
            text("""
            ALTER TABLE products
            ADD CONSTRAINT fk_products_category
            FOREIGN KEY (category) REFERENCES categories(name)
            ON DELETE SET DEFAULT ON UPDATE CASCADE;
        """)
        )
        logger.info(
            "Added foreign key constraint and default value for products category"
        )

    # FTS and fuzzy search extensions
    _ensure_postgres_extensions(conn)
    conn.execute(
        text("""
        CREATE OR REPLACE FUNCTION immutable_unaccent(text)
        RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent', $1) $$;
    """)
    )

    # Check and add embedding column on knowledge_base
    check_emb = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='knowledge_base' AND column_name='embedding';
    """)
    ).first()
    if not check_emb:
        conn.execute(
            text("ALTER TABLE knowledge_base ADD COLUMN embedding vector(1536);")
        )
        # Add index for cosine search operator
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_kb_embedding ON knowledge_base USING ivfflat(embedding vector_cosine_ops) WITH(lists = 100);"
            )
        )
        logger.info("Added 'embedding' vector column to knowledge_base table")

    # search_vector column on knowledge_base
    check_col = conn.execute(
        text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name='knowledge_base' AND column_name='search_vector';
    """)
    ).first()
    if not check_col:
        conn.execute(
            text("""
            ALTER TABLE knowledge_base
            ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('spanish', coalesce(immutable_unaccent(title), '')), 'A') ||
                setweight(to_tsvector('spanish', coalesce(immutable_unaccent(content), '')), 'B') ||
                setweight(to_tsvector('spanish', coalesce(immutable_unaccent(category), '')), 'C')
            ) STORED;
        """)
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_kb_search_vector ON knowledge_base USING GIN(search_vector);"
            )
        )
        logger.info("Created unaccent function and search_vector on knowledge_base")

    # Row Level Security on multi-user tables
    for table in ["conversations", "orders"]:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"))
        conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"))
        conn.execute(text(f"DROP POLICY IF EXISTS user_isolation ON {table};"))
        conn.execute(
            text(
                f"CREATE POLICY user_isolation ON {table} USING (user_id = current_setting('app.current_user_id')::integer);"
            )
        )

    conn.execute(text("ALTER TABLE messages ENABLE ROW LEVEL SECURITY;"))
    conn.execute(text("ALTER TABLE messages FORCE ROW LEVEL SECURITY;"))
    conn.execute(text("DROP POLICY IF EXISTS user_isolation ON messages;"))
    conn.execute(
        text("""
        CREATE POLICY user_isolation ON messages USING (
            conversation_id IN (
                SELECT id FROM conversations
                WHERE user_id = current_setting('app.current_user_id')::integer
            )
        );
    """)
    )

    # Seed admin_chat_ids setting if not exists
    conn.execute(
        text(
            "INSERT INTO system_settings (key, value, description) "
            "VALUES ('admin_chat_ids', '[]', 'List of Telegram chat IDs for system administrators to receive critical notifications') "
            "ON CONFLICT (key) DO NOTHING;"
        )
    )
    conn.execute(
        text(
            "INSERT INTO system_settings (key, value, description) "
            "VALUES ('ui_language', to_json('es-CL'::text), 'Idioma de interfaz y canales conversacionales por defecto') "
            "ON CONFLICT (key) DO NOTHING;"
        )
    )

    logger.info(
        "Fuzzy search and user RLS policies successfully initialized in database"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Context manager de ciclo de vida de la aplicación FastAPI.

    Inicializa y libera todos los recursos de infraestructura.

    Args:
        app: Instancia de la aplicación FastAPI.

    Yields:
        None: Cede el control mientras la app está en ejecución.
    """
    redis_client = None

    try:
        with _sync_engine.begin() as conn:
            _ensure_postgres_extensions(conn)
        # 1. Base de datos — crea tablas según metadata registrada
        Base.metadata.create_all(bind=_sync_engine)
        logger.info("DB tables created/verified")

        # Migraciones DDL en caliente
        with _sync_engine.begin() as conn:
            _run_migrations(conn)
    except Exception as e:
        logger.error("Failed to run database migrations: %s", e)
        raise

    # 2. Seed
    with SessionLocal() as seed_db:
        _seed_business_config(seed_db)
        prime_human_agent_cache(
            BusinessConfigRepository(seed_db).get_config().human_agent_available
        )
        if not settings.is_production or settings.reset_demo_catalog_on_start:
            seed_general(reset_existing_products=True)
        seed_db.commit()
    prime_catalog_cache()

    # 3. Session service
    session_service = create_session_service(config=settings)

    if settings.use_redis_sessions:
        redis_client = create_redis_client()
        await redis_client.ping()
        set_redis_client(redis_client)
        session_service = create_session_service(
            config=settings,
            redis_client=redis_client,
        )
        logger.info("Redis session backend initialized")

    # 4. LLM Provider
    llm_provider = ADKLLMProvider(session_service=session_service)
    set_llm_provider(llm_provider)

    # 5. Cliente HTTP Global (Inicialización Eager / Zero Lazy)
    from app.container import get_http_client

    get_http_client()

    logger.info(
        "ADKLLMProvider initialized — worker PID=%s, model=%s, session_backend=%s",
        os.getpid(),
        settings.model_display,
        settings.session_backend,
    )

    yield

    # Shutdown
    await clear_providers()
    if redis_client is not None:
        await redis_client.aclose()
    logger.info("Application shutdown complete")
