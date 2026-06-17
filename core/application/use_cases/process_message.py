"""
ProcessMessageUseCase — Orquestador central del pipeline de mensajes.

RESPONSABILIDAD ÚNICA: Coordinar el pipeline completo sin saber nada
del canal de entrada ni de la implementación LLM concreta.

Pipeline:
    1. Resolve tenant (plataforma + channel_identifier)
    2. Set tenant context (RLS en PostgreSQL)
    3. Get or create user
    4. Get or create session_id
    5. Build RAG context (base de conocimiento del tenant)
    6. Run LLM inference
    7. Persist conversation record

ANTES: Esta lógica estaba duplicada en chat_controller.py Y telegram_controller.py.
AHORA: Un único lugar, completamente testeable con mocks de los ports.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from application.ports.llm_port import ILLMProvider
from application.ports.rag_port import IRAGProvider
from application.use_cases.commands import ProcessMessageCommand, ProcessMessageResult
from config.database import set_tenant_context
from domain.tenant.schemas import TenantLLMConfig

logger = logging.getLogger(__name__)


class ProcessMessageUseCase:
    """Orquesta el pipeline completo de procesamiento de un mensaje de usuario.

    Recibe ports (interfaces) — no implementaciones concretas —
    lo que permite testear la lógica de orquestación de forma aislada.
    """

    def __init__(
        self,
        db: Session,
        llm_provider: ILLMProvider,
        rag_provider: IRAGProvider,
    ) -> None:
        """Inicializa el use case con sus dependencias inyectadas.

        Args:
            db: Sesión de base de datos (request-scoped).
            llm_provider: Implementación del proveedor LLM.
            rag_provider: Implementación del proveedor RAG.
        """
        self._db = db
        self._llm = llm_provider
        self._rag = rag_provider

    async def execute(self, cmd: ProcessMessageCommand) -> ProcessMessageResult:
        """Ejecuta el pipeline completo de procesamiento.

        Args:
            cmd: Comando con todos los datos del mensaje entrante.

        Returns:
            ProcessMessageResult con la respuesta del LLM y metadata.

        Raises:
            TenantNotFoundError: Si no existe tenant para el canal especificado.
            RuntimeError: Si el LLM provider no puede generar respuesta.
        """
        try:
            # 1. Resolver tenant
            tenant = self._resolve_tenant(cmd.platform, cmd.channel_identifier)

            # 2. Set RLS context en la DB
            set_tenant_context(self._db, str(tenant.id))

            # 3. Get or create user
            user = self._get_or_create_user(
                external_id=cmd.user_id,
                platform=cmd.platform,
                tenant_id=tenant.id,
            )

            # 4. Session ID
            session_id = cmd.session_id or str(uuid.uuid4())

            # 5. Persist conversation si es nueva
            self._ensure_conversation(user_id=user.id, session_id=session_id, tenant_id=tenant.id)

            # 6. RAG context
            rag_context = await self._rag.build_context(
                query=cmd.message,
                tenant_id=tenant.id,
            )

            # 7. Build LLM config desde tenant (retro-compatible con JSON libre)
            llm_config = TenantLLMConfig.from_tenant_config(tenant.config)

            # 8. LLM inference
            response = await self._llm.run_chat(
                llm_config=llm_config,
                user_id=cmd.user_id,
                session_id=session_id,
                message=cmd.message,
                rag_context=rag_context,
            )

            logger.info(
                "Message processed [tenant=%s, user=%s, session=%s, platform=%s]",
                tenant.slug,
                cmd.user_id,
                session_id,
                cmd.platform,
            )

            return ProcessMessageResult(
                response=response,
                session_id=session_id,
                tenant_slug=tenant.slug,
                user_id=cmd.user_id,
            )

        except Exception as e:
            logger.error(
                "ProcessMessageUseCase.execute failed "
                "[platform=%s, channel=%s, user=%s]: %s",
                cmd.platform,
                cmd.channel_identifier,
                cmd.user_id,
                e,
            )
            raise

    def _resolve_tenant(self, platform: str, channel_identifier: str) -> object:
        """Resuelve el tenant a partir de plataforma e identificador de canal.

        Args:
            platform: Canal de entrada (ej: 'telegram').
            channel_identifier: Token/ID que identifica el canal.

        Returns:
            Tenant activo correspondiente.

        Raises:
            TenantNotFoundError: Si no se encuentra tenant para el canal.
        """
        from services.tenant_service import TenantService  # noqa: PLC0415
        from exceptions.tenant_exceptions import TenantNotFoundError  # noqa: PLC0415

        tenant_svc = TenantService(self._db)

        # Intentar resolver por canal (Telegram webhook)
        tenant = tenant_svc.resolve_tenant(platform, channel_identifier)
        if tenant is None:
            # Intentar como tenant_id directo (REST API)
            try:
                tenant_uuid = uuid.UUID(channel_identifier)
                tenant = tenant_svc.get_tenant_by_id(tenant_uuid)
            except ValueError:
                pass

        if tenant is None:
            raise TenantNotFoundError(
                f"No tenant found for platform='{platform}', "
                f"channel_identifier='{channel_identifier}'"
            )
        return tenant

    def _get_or_create_user(
        self,
        external_id: str,
        platform: str,
        tenant_id: uuid.UUID,
    ) -> object:
        """Recupera o crea el usuario para este tenant y plataforma.

        Args:
            external_id: ID externo del usuario en la plataforma.
            platform: Canal de la plataforma.
            tenant_id: UUID del tenant propietario.

        Returns:
            Instancia del modelo User (existente o recién creada).
        """
        from services.user_service import UserService  # noqa: PLC0415

        return UserService(self._db, tenant_id).get_or_create(
            external_id=external_id,
            platform=platform,
        )

    def _ensure_conversation(
        self,
        user_id: uuid.UUID,
        session_id: str,
        tenant_id: uuid.UUID,
    ) -> None:
        """Crea el registro de conversación si no existe para esta sesión.

        Args:
            user_id: UUID interno del usuario.
            session_id: Identificador de la sesión.
            tenant_id: UUID del tenant.
        """
        from services.conversation_service import ConversationService  # noqa: PLC0415

        conv_svc = ConversationService(self._db, tenant_id)
        existing = conv_svc.get_by_session_id(session_id)
        if not existing:
            conv_svc.create_for_user(user_id=user_id, session_id=session_id)
