"""
Container — Registro central de dependencias de la aplicación.

Implementación manual de DI usando funciones factory + lru_cache.
No requiere librerías externas. FastAPI Depends() consume estas factories.

REGLA: Ningún controller importa de `main.py`. Todas las dependencias
se resuelven desde este módulo.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

import httpx
from fastapi import Depends
from sqlalchemy.orm import Session

from config.database import get_db
from infrastructure.rag.kb_rag_provider import KBRAGProvider

logger = logging.getLogger(__name__)


# ============================================================================
# Singletons de infraestructura (inicializados en lifespan)
# ============================================================================

_llm_provider: "ILLMProvider | None" = None  # type: ignore[name-defined]  # noqa: F821
_redis_client: "Redis | None" = None  # type: ignore[name-defined]  # noqa: F821


def set_llm_provider(provider: object) -> None:
    """Registra el LLM provider en el arranque (llamado desde lifespan)."""
    global _llm_provider
    _llm_provider = provider  # type: ignore[assignment]


_http_client: Any = None


def set_redis_client(client: object) -> None:
    """Registra el cliente Redis en el arranque (llamado desde lifespan)."""
    global _redis_client
    _redis_client = client  # type: ignore[assignment]


async def clear_providers() -> None:
    """Limpia los singletons al cerrar la app (llamado desde lifespan)."""
    global _llm_provider, _redis_client, _http_client
    _llm_provider = None
    _redis_client = None
    if _http_client is not None:
        try:
            await _http_client.aclose()
        except Exception as exc:
            logger.exception("Failed to close global HTTP client")
            raise RuntimeError("Failed to close global HTTP client") from exc
        _http_client = None


def get_redis_client() -> Any:
    """Retorna el cliente Redis registrado."""
    return _redis_client


def get_http_client() -> Any:
    """Retorna o inicializa perezosamente el cliente HTTP global para Keep-Alive."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


# ============================================================================
# Provider factories — usadas como Depends() en los routers
# ============================================================================


def get_llm_provider() -> "ILLMProvider":  # type: ignore[name-defined]  # noqa: F821
    """Retorna el LLM provider registrado. Falla rápido si no fue inicializado.

    Returns:
        ILLMProvider: Implementación del proveedor LLM activo.

    Raises:
        RuntimeError: Si el provider no fue inicializado en el lifespan.
    """

    if _llm_provider is None:
        raise RuntimeError(
            "LLM provider not initialized. "
            "Ensure lifespan startup completed successfully."
        )
    return _llm_provider  # type: ignore[return-value]


def get_rag_provider(
    db: Session = Depends(get_db),
) -> "IRAGProvider":  # type: ignore[name-defined]  # noqa: F821
    """Factory de RAG provider con scope de request (necesita db).

    Args:
        db: Sesión de base de datos inyectada por FastAPI.

    Returns:
        IRAGProvider: Implementación de recuperación de contexto RAG.
    """
    return KBRAGProvider(db=db)


def get_process_message_uc(
    db: Session = Depends(get_db),
    llm_provider: object = Depends(get_llm_provider),
    rag_provider: object = Depends(get_rag_provider),
) -> "ProcessMessageUseCase":  # type: ignore[name-defined]  # noqa: F821
    """Factory del use case principal — una instancia por request.

    Args:
        db: Sesión de base de datos.
        llm_provider: Proveedor LLM activo.
        rag_provider: Proveedor RAG activo.

    Returns:
        ProcessMessageUseCase listo para ejecutar.
    """
    # Estas dependencias se resuelven aquí porque el use case arrastra el
    # orquestador LLM/Telegram completo; subirlas al módulo aumentaría el
    # coste de arranque y puede reabrir ciclos con root_agent.
    from application.use_cases.process_message import ProcessMessageUseCase  # noqa: PLC0415
    from services.job_dispatcher import JobDispatcher  # noqa: PLC0415

    return ProcessMessageUseCase(
        db=db,
        llm_provider=llm_provider,  # type: ignore[arg-type]
        rag_provider=rag_provider,  # type: ignore[arg-type]
        job_dispatcher=JobDispatcher(),
    )


def get_telegram_handler(token: str) -> "TelegramChannelHandler":  # type: ignore[name-defined]  # noqa: F821
    """Factory del handler de Telegram para un token específico.

    Args:
        token: Bot token de Telegram que identifica el canal.

    Returns:
        TelegramChannelHandler configurado para ese token.
    """
    # El handler Telegram se instancia por canal/token; mantener la importación
    # en el factory evita cargar esa superficie al inicio del proceso.
    from infrastructure.channels.telegram_handler import TelegramChannelHandler  # noqa: PLC0415

    return TelegramChannelHandler(bot_token=token)


# ============================================================================
# Type aliases para Annotated Depends — uso ergonómico en routers
# ============================================================================

DbDep = Annotated[Session, Depends(get_db)]
LLMProviderDep = Annotated[object, Depends(get_llm_provider)]
RAGProviderDep = Annotated[object, Depends(get_rag_provider)]
ProcessMessageUCDep = Annotated[object, Depends(get_process_message_uc)]
