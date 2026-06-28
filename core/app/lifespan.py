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
    Base.metadata.create_all(bind=_sync_engine)
    logger.info("DB tables created/verified")

    # Run SQL setup for FTS unaccent and search_vector column if missing
    try:
        from sqlalchemy import text
        with _sync_engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent;"))
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION immutable_unaccent(text)
                RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
                AS $$ SELECT public.unaccent('public.unaccent', $1) $$;
            """))
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
    except Exception as e:
        logger.error("Failed to run database FTS unaccent setup: %s", e)

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
