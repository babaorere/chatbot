"""
TelegramConversationFSM — Máquina de estados para conversaciones Telegram.

Implementa el patrón State para gestionar conversaciones híbridas donde
el input puede ser:
  - Texto libre → inferencia LLM
  - Callback de menú → acción predefinida
  - Input contextual esperado por el FSM (ej: nombre de producto)

Los estados se persisten en Redis (o en memoria si no hay Redis)
con el mismo TTL que las sesiones de conversación.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FSMState(str, Enum):
    """Estados posibles de la conversación Telegram."""

    IDLE = "idle"
    """Sin estado especial — input libre va al LLM."""

    AWAITING_PRODUCT_NAME = "awaiting_product_name"
    """El FSM espera que el usuario especifique un producto."""

    AWAITING_CONFIRMATION = "awaiting_confirmation"
    """El FSM espera confirmación sí/no del usuario."""

    AWAITING_CONTACT_INFO = "awaiting_contact_info"
    """El FSM espera datos de contacto del usuario."""

    IN_MENU = "in_menu"
    """El usuario está navegando un menú, aún no ha elegido."""


# Mapeo de callback_data a intención semántica
_CALLBACK_INTENTS: dict[str, str] = {
    "menu:stock": "consultar_stock",
    "menu:precio": "consultar_precio",
    "menu:horario": "get_chatbot_info",
    "menu:contacto": "contactar_humano",
    "menu:inicio": "inicio",
    "confirm:si": "confirmacion_si",
    "confirm:no": "confirmacion_no",
}


class TelegramConversationFSM:
    """Gestiona el estado de una conversación Telegram por usuario.

    Determina cómo debe enrutarse cada input recibido:
    - MENU_ACTION: callback_query con acción predefinida
    - FSM_EXPECTED_INPUT: el FSM aguarda un input específico
    - LLM_INFERENCE: texto libre, va al pipeline LLM normal

    El estado se persiste externamente (Redis recomendado) para
    sobrevivir reinicios del proceso en producción multi-worker.
    """

    def __init__(
        self,
        user_id: str,
        state_store: "FSMStateStore",
    ) -> None:
        """Inicializa el FSM para un usuario específico.

        Args:
            user_id: Identificador del usuario Telegram.
            state_store: Backend de persistencia del estado FSM.
        """
        self._user_id = user_id
        self._store = state_store

    async def get_state(self) -> FSMState:
        """Recupera el estado actual del FSM para este usuario.

        Returns:
            FSMState: Estado actual, IDLE si no hay estado guardado.
        """
        raw = await self._store.get(self._user_id)
        if raw is None:
            return FSMState.IDLE
        try:
            return FSMState(raw.get("state", FSMState.IDLE))
        except ValueError:
            return FSMState.IDLE

    async def set_state(
        self,
        state: FSMState,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Establece un nuevo estado FSM para este usuario.

        Args:
            state: Nuevo estado a establecer.
            context: Datos adicionales del estado (ej: producto consultado).
        """
        import time as ttime
        ctx = context or {}
        ctx["_last_interaction_at"] = ttime.time()
        await self._store.set(
            self._user_id,
            {"state": state.value, "context": ctx},
        )

    async def reset(self) -> None:
        """Resetea el FSM al estado IDLE y limpia el contexto."""
        await self.set_state(FSMState.IDLE)

    async def get_context(self) -> dict[str, Any]:
        """Recupera el contexto del estado actual.

        Returns:
            dict: Datos de contexto almacenados, vacío si no hay estado.
        """
        raw = await self._store.get(self._user_id)
        if raw is None:
            return {}
        return raw.get("context", {})

    async def get_active_menu_id(self) -> int | None:
        """Recupera el ID de mensaje del menú activo actualmente."""
        ctx = await self.get_context()
        return ctx.get("_active_menu_id")

    async def set_active_menu_id(self, message_id: int) -> None:
        """Establece el ID de mensaje del menú activo."""
        ctx = await self.get_context()
        ctx["_active_menu_id"] = message_id
        state = await self.get_state()
        await self.set_state(state, ctx)

    async def get_fsm_version(self) -> int:
        """Recupera la versión/turno actual del FSM."""
        ctx = await self.get_context()
        return ctx.get("_fsm_version", 1)

    async def increment_fsm_version(self) -> int:
        """Incrementa y retorna la nueva versión/turno del FSM."""
        ctx = await self.get_context()
        current = ctx.get("_fsm_version", 1)
        next_ver = current + 1
        ctx["_fsm_version"] = next_ver
        state = await self.get_state()
        await self.set_state(state, ctx)
        return next_ver

    @staticmethod
    def resolve_callback_intent(callback_data: str) -> str | None:
        """Resuelve el intent semántico de un callback_data de Telegram.

        Args:
            callback_data: Dato del callback recibido del botón inline.

        Returns:
            str | None: Intent semántico o None si no está registrado.
        """
        base_data = callback_data.split("#")[0] if "#" in callback_data else callback_data
        return _CALLBACK_INTENTS.get(base_data)

    async def transition(
        self,
        callback_data: str,
    ) -> tuple[FSMState, dict[str, Any]]:
        """Ejecuta una transición de estado basada en un callback de menú.

        Args:
            callback_data: Dato del callback que dispara la transición.

        Returns:
            tuple[FSMState, dict]: Nuevo estado y contexto resultante.
        """
        base_data = callback_data.split("#")[0] if "#" in callback_data else callback_data
        intent = self.resolve_callback_intent(base_data)

        transitions: dict[str, FSMState] = {
            "consultar_stock": FSMState.AWAITING_PRODUCT_NAME,
            "consultar_precio": FSMState.AWAITING_PRODUCT_NAME,
            "contactar_humano": FSMState.IDLE,
            "get_chatbot_info": FSMState.IDLE,
            "inicio": FSMState.IDLE,
            "confirmacion_si": FSMState.IDLE,
            "confirmacion_no": FSMState.IDLE,
        }

        next_state = transitions.get(intent or "", FSMState.IDLE)
        
        # Recuperar y actualizar el contexto existente para no perder variables ni _active_menu_id
        context = await self.get_context()
        context.update({"intent": intent, "callback": base_data})
        
        # Incrementar versión en transición
        current_version = context.get("_fsm_version", 1)
        context["_fsm_version"] = current_version + 1

        await self.set_state(next_state, context)
        logger.debug(
            "FSM transition [user=%s]: callback='%s' → state=%s, version=%d",
            self._user_id,
            callback_data,
            next_state.value,
            context["_fsm_version"],
        )
        return next_state, context


# ============================================================================
# State Store — abstracción de persistencia del estado FSM
# ============================================================================


class FSMStateStore:
    """Abstracción de persistencia del estado FSM.

    Implementación base en memoria. En producción, usar RedisStateStore.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    async def get(self, user_id: str) -> dict[str, Any] | None:
        """Recupera el estado del usuario.

        Args:
            user_id: Identificador del usuario.

        Returns:
            dict | None: Estado guardado o None si no existe.
        """
        return self._store.get(user_id)

    async def set(self, user_id: str, data: dict[str, Any]) -> None:
        """Guarda el estado del usuario.

        Args:
            user_id: Identificador del usuario.
            data: Datos del estado a persistir.
        """
        self._store[user_id] = data

    async def delete(self, user_id: str) -> None:
        """Elimina el estado del usuario.

        Args:
            user_id: Identificador del usuario.
        """
        self._store.pop(user_id, None)


class RedisFSMStateStore(FSMStateStore):
    """State store respaldado por Redis para producción multi-worker."""

    def __init__(
        self, redis_client: Any, namespace: str, ttl_seconds: int = 86400
    ) -> None:
        """Inicializa el store Redis.

        Args:
            redis_client: Cliente Redis async.
            namespace: Prefijo de namespace para las claves Redis.
            ttl_seconds: TTL de los estados FSM en segundos.
        """
        super().__init__()
        self._redis = redis_client
        self._namespace = namespace.rstrip(":")
        self._ttl = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"{self._namespace}:fsm:{user_id}"

    async def get(self, user_id: str) -> dict[str, Any] | None:
        raw = await self._redis.get(self._key(user_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def set(self, user_id: str, data: dict[str, Any]) -> None:
        await self._redis.set(
            self._key(user_id),
            json.dumps(data),
            ex=self._ttl,
        )

    async def delete(self, user_id: str) -> None:
        await self._redis.delete(self._key(user_id))
