"""
lifespan — Bootstrap de la aplicación FastAPI.

Extrae la lógica de inicialización/shutdown de main.py.
El orden de inicialización es:
1. DB: tablas + RLS
2. Seed del tenant por defecto (si no existe)
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

from config.database import _sync_engine, Base, enable_rls_on_startup, SessionLocal
from config.redis import create_redis_client
from config.settings import settings
from app.container import set_llm_provider, set_redis_client, clear_providers

logger = logging.getLogger(__name__)


def _seed_default_tenant(db: Session) -> None:
    """Crea el tenant por defecto si no existe ninguno activo.

    Separado de main.py para mantener main limpio y este módulo testeable.

    Args:
        db: Sesión de base de datos sincrónica.
    """
    from services.tenant_service import TenantService  # noqa: PLC0415

    tenant_service = TenantService(db)
    existing = tenant_service.list_active_tenants()
    if existing:
        return

    default_tenant = tenant_service.create_tenant(
        slug="el_buen_trago",
        name="Botillería El Buen Trago",
        config={
            "instruction": (
                "Eres el asistente virtual de la Botillería El Buen Trago. "
                "Tu rol es atender consultas de clientes, ayudar con pedidos de productos, "
                "resolver dudas sobre horarios y disponibilidad, y mantener un tono amable y profesional.\n\n"
                "INFORMACIÓN DE LA BOTILLERÍA:\n"
                "- Horario: Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00\n"
                "- Servicios: Venta de licores, cervezas artesanales, vinos, pedidos a domicilio\n"
                "- Ubicación: Santiago, Chile\n\n"
                "REGLAS:\n"
                "1. NUNCA inventes precios ni stock. Si no sabes algo, sé honesto.\n"
                "2. Si te preguntan por disponibilidad, indica que consultarás y responderás pronto.\n"
                "3. Mantén un tono amable, profesional y cercano.\n"
                "4. Si el usuario pide algo fuera de scope, ofrece contactar a un humano.\n"
                "5. Responde en español siempre."
            ),
            "model": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
            "api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "products": [],
        },
    )
    tenant_service.add_channel_route(
        tenant_id=default_tenant.id,
        platform="telegram",
        channel_identifier=os.getenv("TELEGRAM_BOT_TOKEN", "default_token"),
    )
    logger.info("Default tenant created: el_buen_trago")


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

    with _sync_engine.begin() as conn:
        enable_rls_on_startup(conn)
    logger.info("Row-Level Security policies enabled")

    # 2. Seed
    with SessionLocal() as seed_db:
        _seed_default_tenant(seed_db)
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
