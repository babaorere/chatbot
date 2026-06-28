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
from sqlalchemy.orm import Session

from config.database import _sync_engine, Base, SessionLocal
from config.redis import create_redis_client
from config.settings import settings
from app.container import set_llm_provider, set_redis_client, clear_providers

logger = logging.getLogger(__name__)


def _seed_business_config(db: Session) -> None:
    """Crea la configuración del negocio por defecto si no existe."""
    from repositories.business_config_repository import BusinessConfigRepository  # noqa: PLC0415

    repo = BusinessConfigRepository(db)
    repo.get_config()
    logger.info("Business configuration verified/seeded")


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

    # 1. Base de datos
    from models.category import Category  # noqa: F401
    Base.metadata.create_all(bind=_sync_engine)
    logger.info("DB tables created/verified")

    # Run SQL setup for FTS unaccent and search_vector column if missing
    try:
        from sqlalchemy import text
        with _sync_engine.begin() as conn:
            # Seed default 'General' category first
            conn.execute(text("INSERT INTO categories (name, slug, is_system) VALUES ('General', 'general', true) ON CONFLICT (name) DO NOTHING;"))
            
            # Migrate existing categories from products table
            conn.execute(text("""
                INSERT INTO categories (name, slug, is_system)
                SELECT DISTINCT category, LOWER(category), false
                FROM products
                WHERE category IS NOT NULL AND category NOT IN (SELECT name FROM categories)
                ON CONFLICT (name) DO NOTHING;
            """))

            # Ensure default value of products.category is 'General'
            conn.execute(text("ALTER TABLE products ALTER COLUMN category SET DEFAULT 'General';"))

            # Add foreign key constraint if not exists
            check_fk = conn.execute(text("""
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_category';
            """)).first()
            if not check_fk:
                # Update any null categories to 'General' to satisfy constraint
                conn.execute(text("UPDATE products SET category = 'General' WHERE category IS NULL;"))
                conn.execute(text("""
                    ALTER TABLE products 
                    ADD CONSTRAINT fk_products_category 
                    FOREIGN KEY (category) REFERENCES categories(name) 
                    ON DELETE SET DEFAULT ON UPDATE CASCADE;
                """))
                logger.info("Added foreign key constraint and default value for products category")

            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent;"))
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION immutable_unaccent(text)
                RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
                AS $$ SELECT public.unaccent('public.unaccent', $1) $$;
            """))
            # Enable pg_trgm for fuzzy search similarity
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            # Check if search_vector column exists on knowledge_base table
            check_col = conn.execute(text("""
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='knowledge_base' AND column_name='search_vector';
            """)).first()
            if not check_col:
                conn.execute(text("""
                    ALTER TABLE knowledge_base 
                    ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('spanish', coalesce(immutable_unaccent(title), '')), 'A') ||
                        setweight(to_tsvector('spanish', coalesce(immutable_unaccent(content), '')), 'B') ||
                        setweight(to_tsvector('spanish', coalesce(immutable_unaccent(category), '')), 'C')
                    ) STORED;
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kb_search_vector ON knowledge_base USING GIN(search_vector);"))
                logger.info("Created unaccent function and search_vector on knowledge_base")

            # Enable RLS policies on multi-user tables
            for table in ["conversations", "orders"]:
                conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"))
                conn.execute(text(f"DROP POLICY IF EXISTS user_isolation ON {table};"))
                conn.execute(text(f"CREATE POLICY user_isolation ON {table} USING (user_id = current_setting('app.current_user_id')::integer);"))

            # Enable RLS on messages using subquery matching conversations
            conn.execute(text("ALTER TABLE messages ENABLE ROW LEVEL SECURITY;"))
            conn.execute(text("DROP POLICY IF EXISTS user_isolation ON messages;"))
            conn.execute(text("""
                CREATE POLICY user_isolation ON messages USING (
                    conversation_id IN (
                        SELECT id FROM conversations 
                        WHERE user_id = current_setting('app.current_user_id')::integer
                    )
                );
            """))

            logger.info("Fuzzy search and user RLS policies successfully initialized in database")
    except Exception as e:
        logger.error("Failed to run database FTS unaccent, pg_trgm, or RLS setups: %s", e)

    # 2. Seed
    with SessionLocal() as seed_db:
        _seed_business_config(seed_db)
        seed_db.commit()

    # 3. Session service
    from services.session_service_factory import create_session_service  # noqa: PLC0415

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
    from infrastructure.llm.adk_provider import ADKLLMProvider  # noqa: PLC0415

    llm_provider = ADKLLMProvider(session_service=session_service)
    set_llm_provider(llm_provider)

    logger.info(
        "ADKLLMProvider initialized — worker PID=%s, model=%s, session_backend=%s",
        os.getpid(),
        settings.model_display,
        settings.session_backend,
    )

    yield

    # Shutdown
    clear_providers()
    if redis_client is not None:
        await redis_client.aclose()
    logger.info("Application shutdown complete")
