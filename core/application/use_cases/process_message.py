"""
ProcessMessageUseCase — Orquestador central del pipeline de mensajes.

RESPONSABILIDAD ÚNICA: Coordinar el pipeline completo sin saber nada
del canal de entrada ni de la implementación LLM concreta.

Pipeline:
    1. Get or create user
    2. Get or create session_id
    3. Build RAG context only for general-service questions
    4. Run LLM inference
    5. Persist conversation record
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from application.ports.llm_port import ILLMProvider
from application.ports.rag_port import IRAGProvider
from application.use_cases.commands import ProcessMessageCommand, ProcessMessageResult
from services.job_dispatcher import JobDispatcher
from services.rag_policy import RAGIntent, RAGPolicyService

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
        job_dispatcher: JobDispatcher | None = None,
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
        self._job_dispatcher = job_dispatcher or JobDispatcher()

    async def execute(self, cmd: ProcessMessageCommand) -> ProcessMessageResult:
        """Ejecuta el pipeline completo de procesamiento.

        Args:
            cmd: Comando con todos los datos del mensaje entrante.

        Returns:
            ProcessMessageResult con la respuesta del LLM y metadata.
        """
        try:
            # 1. Get or create user
            user = self._get_or_create_user(
                external_id=cmd.user_id,
                platform=cmd.platform,
            )

            # Set user context in the session for Postgres Row-Level Security (RLS)
            from sqlalchemy import text

            self._db.execute(
                text("SET app.current_user_id = :user_id"), {"user_id": user.id}
            )

            # 2. Session ID
            session_id = cmd.session_id or str(uuid.uuid4())

            # Set contextvar for GADK tool invocation
            from agents.root_agent import current_session_id_var

            current_session_id_var.set(session_id)

            # 3. Persist conversation si es nueva
            self._ensure_conversation(user_id=user.id, session_id=session_id)

            # Check if bot is paused for this conversation (Human Takeover active)
            from services.conversation_service import ConversationService

            conv_svc = ConversationService(self._db)
            conv = conv_svc.get_by_session_id(session_id)
            if conv and getattr(conv, "is_bot_paused", False) is True:
                logger.info(
                    "Chatbot is paused (human takeover active) for user %s / session %s",
                    cmd.user_id,
                    session_id,
                )
                return ProcessMessageResult(
                    user_id=cmd.user_id,
                    session_id=session_id,
                    response="",
                )

            # 4. RAG context — policy check before retrieval
            rag_policy = RAGPolicyService()
            rag_result = rag_policy.classify(query=cmd.message)

            rag_context: str | None = None
            if rag_result.intent == RAGIntent.GENERAL_SERVICE:
                rag_context = await self._rag.build_context(
                    query=cmd.message,
                )
            else:
                logger.debug(
                    "RAG skipped per policy [intent=%s, reason='%s', query='%s']",
                    rag_result.intent,
                    rag_result.reason,
                    cmd.message[:80],
                )

            # 5. LLM inference
            import time
            from services.alert_service import AlertService

            start_time = time.perf_counter()
            try:
                response = await self._llm.run_chat(
                    user_id=cmd.user_id,
                    session_id=session_id,
                    message=cmd.message,
                    rag_context=rag_context,
                )
            except Exception as e:
                await self._dispatch_llm_failure_alert(
                    error=e,
                    user_id=cmd.user_id,
                    session_id=session_id,
                )
                raise

            duration = time.perf_counter() - start_time
            if duration >= AlertService.LATENCY_THRESHOLD_SECONDS:
                await self._dispatch_llm_latency_alert(
                    duration=duration,
                    user_id=cmd.user_id,
                    session_id=session_id,
                )

            logger.info(
                "Message processed [user=%s, session=%s, platform=%s]",
                cmd.user_id,
                session_id,
                cmd.platform,
            )

            return ProcessMessageResult(
                response=response,
                session_id=session_id,
                user_id=cmd.user_id,
            )

        except Exception as e:
            logger.error(
                "ProcessMessageUseCase.execute failed [platform=%s, user=%s]: %s",
                cmd.platform,
                cmd.user_id,
                e,
            )
            raise

    async def _dispatch_llm_failure_alert(
        self,
        *,
        error: Exception,
        user_id: str,
        session_id: str,
    ) -> None:
        from services.alert_service import AlertService  # noqa: PLC0415

        title = "Fallo en la inferencia del LLM"
        details = (
            f"Ocurrió un error al llamar al LLM.\n\n"
            f"❌ *Error:* `{error}`\n"
            f"👤 *User ID:* `{user_id}`\n"
            f"💬 *Session ID:* `{session_id}`"
        )
        event_id = str(uuid.uuid4())
        try:
            await self._job_dispatcher.enqueue_job(
                "job_notify_critical_issue",
                title=title,
                details=details,
                alert_type="error",
                user_id=user_id,
                session_id=session_id,
                event_id=event_id,
                _job_id=f"alert:error:{event_id}",
            )
        except RuntimeError:
            await AlertService.notify_critical_issue(
                db=self._db,
                title=title,
                details=details,
                alert_type="error",
            )

    async def _dispatch_llm_latency_alert(
        self,
        *,
        duration: float,
        user_id: str,
        session_id: str,
    ) -> None:
        from services.alert_service import AlertService  # noqa: PLC0415

        event_id = str(uuid.uuid4())
        try:
            await self._job_dispatcher.enqueue_job(
                "job_check_llm_latency",
                duration=duration,
                user_id=user_id,
                session_id=session_id,
                event_id=event_id,
                _job_id=f"alert:latency:{event_id}",
            )
        except RuntimeError:
            await AlertService.check_llm_latency(
                db=self._db,
                duration=duration,
                user_id=user_id,
                session_id=session_id,
            )

    async def clear_session(self, user_id: str, session_id: str) -> None:
        """Limpia la sesión de conversación del LLM."""
        try:
            await self._llm.clear_session(user_id=user_id, session_id=session_id)
            logger.info(
                "Cleared conversation session for user %s, session %s",
                user_id,
                session_id,
            )
        except Exception as e:
            logger.error("Failed to clear session in UseCase: %s", e)

    def _get_or_create_user(
        self,
        external_id: str,
        platform: str,
    ) -> object:
        """Recupera o crea el usuario.

        Args:
            external_id: ID externo del usuario en la plataforma.
            platform: Canal de la plataforma.

        Returns:
            Instancia del modelo User.
        """
        from services.user_service import UserService  # noqa: PLC0415

        return UserService(self._db).get_or_create(
            external_id=external_id,
            platform=platform,
        )

    def _ensure_conversation(
        self,
        user_id: int,
        session_id: str,
    ) -> None:
        """Crea el registro de conversación si no existe para esta sesión.

        Args:
            user_id: ID interno del usuario.
            session_id: Identificador de la sesión.
        """
        from services.conversation_service import ConversationService  # noqa: PLC0415

        conv_svc = ConversationService(self._db)
        existing = conv_svc.get_by_session_id(session_id)
        if not existing:
            conv_svc.create_for_user(user_id=user_id, session_id=session_id)
