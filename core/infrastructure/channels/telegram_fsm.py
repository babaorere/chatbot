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
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FSMState(str, Enum):
    """Estados posibles de la conversación Telegram."""

    IDLE = "idle"
    """Sin estado especial — input libre va al LLM."""

    AWAITING_PRODUCT_NAME = "awaiting_product_name"
    """El FSM espera que el usuario especifique un producto."""

    AWAITING_QUANTITY = "awaiting_quantity"
    """El FSM espera que el usuario indique una cantidad válida."""

    AWAITING_CONFIRMATION = "awaiting_confirmation"
    """El FSM espera confirmación sí/no del usuario."""

    AWAITING_CONTACT_INFO = "awaiting_contact_info"
    """El FSM espera datos de contacto del usuario."""

    AWAITING_ORDER_ID = "awaiting_order_id"
    """El FSM espera que el usuario ingrese un ID de pedido válido."""

    IN_MENU = "in_menu"
    """El usuario está navegando un menú, aún no ha elegido."""


class ExpectedInput(str, Enum):
    """Tipo de input esperado por el FSM en el turno actual."""

    FREE_TEXT = "free_text"
    MENU_SELECTION = "menu_selection"
    PRODUCT_NAME = "product_name"
    QUANTITY = "quantity"
    CONFIRMATION = "confirmation"
    ORDER_ID = "order_id"


@dataclass(frozen=True)
class TelegramFSMRuntimeSnapshot:
    """Lectura compuesta del FSM para evitar I/O secuencial en un turno."""

    state: FSMState
    context: dict[str, Any]
    active_menu_id: int | None
    fsm_version: int
    menu_stack: list[str]
    menu_scope: str | None
    expected_input: ExpectedInput
    allow_numeric_input: bool


# Mapeo de callback_data a intención semántica
_CALLBACK_INTENTS: dict[str, str] = {
    "menu:stock": "consultar_stock",
    "menu:precio": "consultar_precio",
    "menu:horario": "get_chatbot_info",
    "menu:contacto": "contactar_humano",
    "menu:promociones": "mostrar_promociones",
    "menu:mas_vendidos": "mostrar_mas_vendidos",
    "menu:favoritos": "mostrar_favoritos",
    "menu:carrito": "mostrar_carrito",
    "menu:inicio": "inicio",
    "confirm:si": "confirmacion_si",
    "confirm:no": "confirmacion_no",
    "menu:pedidos": "mostrar_pedidos",
    "menu:buscar_pedido_prompt": "buscar_pedido_prompt",
    "menu:cancelar_pedido_prompt": "cancelar_pedido_prompt",
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
        state_value = raw.get("state", FSMState.IDLE)
        try:
            return FSMState(state_value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid FSM state stored for user {self._user_id}: {state_value!r}"
            ) from exc

    async def get_state_and_context(self) -> tuple[FSMState, dict[str, Any]]:
        """Recupera estado y contexto con una sola lectura del store."""
        raw = await self._store.get(self._user_id)
        if raw is None:
            return FSMState.IDLE, {}
        state_value = raw.get("state", FSMState.IDLE)
        try:
            state = FSMState(state_value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid FSM state stored for user {self._user_id}: {state_value!r}"
            ) from exc
        context = raw.get("context", {}) or {}
        if not isinstance(context, dict):
            raise ValueError(
                f"Invalid FSM context stored for user {self._user_id}: {type(context).__name__}"
            )
        return state, context

    async def get_runtime_snapshot(self) -> TelegramFSMRuntimeSnapshot:
        """Carga estado, contexto y metadata de menú con una sola lectura."""
        state, context = await self.get_state_and_context()
        stack = context.get("_menu_stack", [])
        if not isinstance(stack, list):
            raise ValueError(
                f"Invalid FSM menu stack stored for user {self._user_id}: {type(stack).__name__}"
            )
        menu_scope = context.get("_menu_scope")
        if not isinstance(menu_scope, str) or not menu_scope:
            menu_scope = None
        expected_input_value = context.get(
            "_expected_input",
            ExpectedInput.FREE_TEXT.value,
        )
        return TelegramFSMRuntimeSnapshot(
            state=state,
            context=context.copy(),
            active_menu_id=context.get("_active_menu_id"),
            fsm_version=context.get("_fsm_version", 1),
            menu_stack=[item for item in stack if isinstance(item, str) and item],
            menu_scope=menu_scope,
            expected_input=ExpectedInput(expected_input_value),
            allow_numeric_input=bool(context.get("_allow_numeric_input", False)),
        )

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
        ctx = context or {}
        ctx["_last_interaction_at"] = time.time()
        await self._store.set(
            self._user_id,
            {"state": state.value, "context": ctx},
        )

    async def update_state(
        self,
        mutator: Callable[[FSMState, dict[str, Any]], tuple[FSMState, dict[str, Any]]],
    ) -> tuple[FSMState, dict[str, Any]]:
        """Actualiza estado y contexto en una sola operación lógica."""

        async def _apply(raw: dict[str, Any] | None) -> dict[str, Any]:
            if raw is None:
                current_state = FSMState.IDLE
                current_context: dict[str, Any] = {}
            else:
                current_state = FSMState(raw.get("state", FSMState.IDLE))
                current_context = raw.get("context", {}) or {}
                if not isinstance(current_context, dict):
                    raise ValueError(
                        f"Invalid FSM context stored for user {self._user_id}: {type(current_context).__name__}"
                    )
            next_state, next_context = mutator(current_state, current_context.copy())
            next_context["_last_interaction_at"] = time.time()
            return {"state": next_state.value, "context": next_context}

        payload = await self._store.update(self._user_id, _apply)
        state = FSMState(payload["state"])
        context = payload.get("context", {}) or {}
        return state, context

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
        context = raw.get("context", {})
        if not isinstance(context, dict):
            raise ValueError(
                f"Invalid FSM context stored for user {self._user_id}: {type(context).__name__}"
            )
        return context

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

    async def persist_menu_metadata(
        self,
        *,
        version: int,
        options: list[str],
        active_menu_id: int,
        state: FSMState | None = None,
        menu_scope: str | None = None,
        menu_stack: list[str] | None = None,
        expected_input: ExpectedInput = ExpectedInput.MENU_SELECTION,
        allow_numeric_input: bool = True,
    ) -> None:
        """Guarda de una sola vez la metadata del menú activo en el FSM."""

        def mutate(
            current_state: FSMState,
            context: dict[str, Any],
        ) -> tuple[FSMState, dict[str, Any]]:
            context["_fsm_version"] = version
            context["_menu_options"] = options
            context["_active_menu_id"] = active_menu_id
            context["_menu_scope"] = (
                menu_scope if menu_scope is not None else context.get("_menu_scope")
            )
            context["_menu_stack"] = (
                menu_stack
                if menu_stack is not None
                else ([menu_scope] if menu_scope else context.get("_menu_stack", []))
            )
            context["_expected_input"] = expected_input.value
            context["_allow_numeric_input"] = allow_numeric_input
            return state or FSMState.IN_MENU, context

        await self.update_state(mutate)

    async def get_expected_input(self) -> ExpectedInput:
        """Recupera el tipo de input esperado en el estado actual."""
        context = await self.get_context()
        value = context.get("_expected_input", ExpectedInput.FREE_TEXT.value)
        return ExpectedInput(value)

    async def get_menu_scope(self) -> str | None:
        """Recupera el scope del menú activo."""
        context = await self.get_context()
        scope = context.get("_menu_scope")
        return scope if isinstance(scope, str) and scope else None

    async def get_menu_stack(self) -> list[str]:
        """Recupera la pila de navegación del menú activo."""
        context = await self.get_context()
        stack = context.get("_menu_stack", [])
        if not isinstance(stack, list):
            raise ValueError(
                f"Invalid FSM menu stack stored for user {self._user_id}: {type(stack).__name__}"
            )
        return [item for item in stack if isinstance(item, str) and item]

    async def resolve_legacy_numeric_menu_selection(
        self,
        text: str,
    ) -> str | None:
        """Resuelve un input numérico o de atajo de teclado al callback del menú activo."""
        # Normalizar acentos y pasar a minúsculas
        import unicodedata

        normalized = "".join(
            c
            for c in unicodedata.normalize("NFD", text.strip().lower())
            if unicodedata.category(c) != "Mn"
        )
        if normalized in {"v", "volver"}:
            return "menu:back"
        if normalized in {"m", "menu"}:
            return "menu:home"

        if not normalized.isdigit():
            return None
        state, context = await self.get_state_and_context()
        if state != FSMState.IN_MENU or not context.get("_allow_numeric_input", False):
            return None
        options = context.get("_menu_options", [])
        if not isinstance(options, list):
            raise ValueError(
                f"Invalid FSM menu options stored for user {self._user_id}: {type(options).__name__}"
            )
        index = int(normalized) - 1
        if 0 <= index < len(options):
            option = options[index]
            return option if isinstance(option, str) else None
        return None

    @staticmethod
    def resolve_callback_intent(callback_data: str) -> str | None:
        """Resuelve el intent semántico de un callback_data de Telegram.

        Args:
            callback_data: Dato del callback recibido del botón inline.

        Returns:
            str | None: Intent semántico o None si no está registrado.
        """
        base_data = (
            callback_data.split("#")[0] if "#" in callback_data else callback_data
        )
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
        base_data = (
            callback_data.split("#")[0] if "#" in callback_data else callback_data
        )
        intent = self.resolve_callback_intent(base_data)

        transitions: dict[str, FSMState] = {
            "consultar_stock": FSMState.AWAITING_PRODUCT_NAME,
            "consultar_precio": FSMState.AWAITING_PRODUCT_NAME,
            "contactar_humano": FSMState.IDLE,
            "get_chatbot_info": FSMState.IDLE,
            "inicio": FSMState.IDLE,
            "confirmacion_si": FSMState.IDLE,
            "confirmacion_no": FSMState.IDLE,
            "buscar_pedido_prompt": FSMState.AWAITING_ORDER_ID,
            "cancelar_pedido_prompt": FSMState.AWAITING_ORDER_ID,
        }

        if intent is None:
            current_state, context = await self.get_state_and_context()
            return current_state, context

        next_state = transitions.get(intent, FSMState.IDLE)

        def mutate(
            current_state: FSMState,
            context: dict[str, Any],
        ) -> tuple[FSMState, dict[str, Any]]:
            context.update({"intent": intent, "callback": base_data})
            current_version = context.get("_fsm_version", 1)
            context["_fsm_version"] = current_version + 1
            if next_state != FSMState.IN_MENU:
                if next_state == FSMState.AWAITING_PRODUCT_NAME:
                    context["_expected_input"] = ExpectedInput.PRODUCT_NAME.value
                elif next_state == FSMState.AWAITING_ORDER_ID:
                    context["_expected_input"] = ExpectedInput.ORDER_ID.value
                else:
                    context["_expected_input"] = ExpectedInput.FREE_TEXT.value
            return next_state, context

        _, context = await self.update_state(mutate)
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

    async def update(
        self,
        user_id: str,
        updater: Callable[[dict[str, Any] | None], Any],
    ) -> dict[str, Any]:
        """Aplica una mutación lógica sobre el estado almacenado."""
        current = self._store.get(user_id)
        next_value = await updater(current)
        self._store[user_id] = next_value
        return next_value

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
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(
                f"Invalid FSM payload stored in Redis for user {user_id}"
            ) from exc

    async def set(self, user_id: str, data: dict[str, Any]) -> None:
        await self._redis.set(
            self._key(user_id),
            json.dumps(data),
            ex=self._ttl,
        )

    async def update(
        self,
        user_id: str,
        updater: Callable[[dict[str, Any] | None], Any],
    ) -> dict[str, Any]:
        key = self._key(user_id)
        while True:
            async with self._redis.pipeline() as pipe:
                try:
                    await pipe.watch(key)
                    raw = await self._redis.get(key)
                    current = None
                    if raw is not None:
                        try:
                            current = json.loads(raw)
                        except (json.JSONDecodeError, TypeError) as exc:
                            raise ValueError(
                                f"Invalid FSM payload stored in Redis for user {user_id}"
                            ) from exc
                    next_value = await updater(current)
                    pipe.multi()
                    pipe.set(key, json.dumps(next_value), ex=self._ttl)
                    await pipe.execute()
                    return next_value
                except Exception as exc:
                    watch_error_name = exc.__class__.__name__
                    if watch_error_name == "WatchError":
                        continue
                    raise

    async def delete(self, user_id: str) -> None:
        await self._redis.delete(self._key(user_id))
