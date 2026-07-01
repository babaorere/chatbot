"""
telegram_controller — Webhook handler para Telegram.

Recibe actualizaciones de Telegram, resuelve el FSM (menús vs texto libre),
y delega la inferencia y reglas de negocio a ProcessMessageUseCase.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from app.container import ProcessMessageUCDep, get_redis_client
from application.use_cases.commands import ProcessMessageCommand
from infrastructure.channels.telegram_fsm import (
    TelegramConversationFSM,
    FSMStateStore,
    FSMState,
    RedisFSMStateStore,
)
from config.settings import settings
from services.telegram_service import (
    send_telegram_message,
    build_main_menu,
    inject_version_to_reply_markup,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

_memory_fsm_store = FSMStateStore()

# Cerradura local en memoria para concurrencia si Redis no está activo
_local_locks: set[str] = set()


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _log_timing(
    *,
    trace_id: str,
    stage: str,
    started_at: float,
    user_id: str | None = None,
    extra: str = "",
) -> None:
    suffix = f" {extra}" if extra else ""
    logger.info(
        "[telegram_timing] trace=%s stage=%s elapsed_ms=%.2f user=%s%s",
        trace_id,
        stage,
        _elapsed_ms(started_at),
        user_id or "-",
        suffix,
    )


def get_fsm_store() -> FSMStateStore:
    """Returns the Redis-backed FSM state store if configured, otherwise falls back to in-memory."""
    if settings.use_redis_sessions:
        redis_client = get_redis_client()
        if redis_client is not None:
            return RedisFSMStateStore(
                redis_client=redis_client,
                namespace=settings.redis_namespace,
                ttl_seconds=settings.redis_session_ttl_seconds,
            )
    return _memory_fsm_store


async def send_menu_message(
    bot_token: str,
    chat_id: int | str,
    text: str,
    reply_markup: dict | None,
    fsm: TelegramConversationFSM,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> int | None:
    """Wrapper para enviar mensajes. Si contiene reply_markup, inyecta la versión del FSM

    e incrementa el contador, guardando el message_id resultante como el menú activo.
    También persiste las opciones en el FSM context para soporte híbrido numérico.
    """
    started_at = time.perf_counter()
    menu_version: int | None = None
    menu_options: list[str] = []
    if reply_markup and "inline_keyboard" in reply_markup:
        _, context = await fsm.get_state_and_context()
        menu_version = context.get("_fsm_version", 1) + 1
        reply_markup = inject_version_to_reply_markup(reply_markup, menu_version)

        # Extraer y guardar callback_data para entrada numérica híbrida
        for row in reply_markup["inline_keyboard"]:
            for btn in row:
                if "callback_data" in btn:
                    cb = btn["callback_data"]
                    base = cb.split("#")[0]
                    menu_options.append(base)
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="menu_prepare",
                started_at=started_at,
                user_id=user_id,
                extra=f"version={menu_version} options={len(menu_options)}",
            )

    msg_id = await send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        trace_id=trace_id,
    )

    if (
        msg_id
        and reply_markup
        and "inline_keyboard" in reply_markup
        and menu_version is not None
    ):
        await fsm.persist_menu_metadata(
            version=menu_version,
            options=menu_options,
            active_menu_id=msg_id,
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="menu_metadata_persisted",
                started_at=started_at,
                user_id=user_id,
                extra=f"message_id={msg_id}",
            )
    elif trace_id:
        _log_timing(
            trace_id=trace_id,
            stage="menu_send_completed",
            started_at=started_at,
            user_id=user_id,
            extra=f"message_id={msg_id}",
        )

    return msg_id


_human_agent_cache: dict[str, Any] = {"value": True, "expires_at": 0}


def _get_human_agent_available() -> bool:
    """Retrieves whether a human agent is currently available from business configuration with caching."""
    global _human_agent_cache
    now = time.time()
    if now < _human_agent_cache["expires_at"]:
        return _human_agent_cache["value"]

    from config.database import SessionLocal
    from services.business_config_service import BusinessConfigService

    db = SessionLocal()
    try:
        cfg_svc = BusinessConfigService(db)
        cfg = cfg_svc.get_config()
        val = cfg.human_agent_available if cfg else True
        _human_agent_cache = {"value": val, "expires_at": now + 300}
        return val
    except Exception:
        return True
    finally:
        db.close()


async def _clear_latest_conversation_session(
    user_id: str,
    trace_id: str | None = None,
    reason: str = "manual_reset",
) -> None:
    """Programa o ejecuta el clear de la sesión conversacional más reciente."""
    started_at = time.perf_counter()
    from services.conversation_reset_service import clear_latest_conversation_session
    from services.job_dispatcher import JobDispatcher

    event_id = str(uuid.uuid4())

    try:
        await JobDispatcher().enqueue_job(
            "job_clear_latest_conversation_session",
            user_id=user_id,
            trace_id=trace_id,
            reason=reason,
            event_id=event_id,
            _job_id=f"session-clear:{event_id}",
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="session_clear_enqueued",
                started_at=started_at,
                user_id=user_id,
                extra=f"reason={reason} event_id={event_id}",
            )
    except RuntimeError:
        session_id = await clear_latest_conversation_session(user_id)
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="session_clear_fallback_done",
                started_at=started_at,
                user_id=user_id,
                extra=f"reason={reason} session_id={session_id or '-'}",
            )
    except Exception as exc:
        logger.error(
            "Failed to clear latest conversation session [user=%s]: %s",
            user_id,
            exc,
        )


async def _clear_reply_markup_async(
    *,
    token: str,
    chat_id: Any,
    message_id: int,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Limpia el teclado inline fuera del camino crítico del callback."""
    from services.telegram_service import clear_telegram_reply_markup

    started_at = time.perf_counter()
    try:
        await clear_telegram_reply_markup(
            bot_token=token,
            chat_id=chat_id,
            message_id=message_id,
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="reply_markup_cleared_async",
                started_at=started_at,
                user_id=user_id,
                extra=f"message_id={message_id}",
            )
    except Exception as exc:
        logger.error(
            "Failed to clear reply markup asynchronously [user=%s, message_id=%s]: %s",
            user_id,
            message_id,
            exc,
        )


async def _defer_clear_reply_markup(
    *,
    token: str,
    chat_id: Any,
    message_id: int,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Programa la limpieza del teclado inline con job durable o fallback local."""
    from services.job_dispatcher import JobDispatcher

    started_at = time.perf_counter()
    event_id = str(uuid.uuid4())
    try:
        await JobDispatcher().enqueue_job(
            "job_clear_reply_markup",
            token=token,
            chat_id=chat_id,
            message_id=message_id,
            trace_id=trace_id,
            user_id=user_id,
            event_id=event_id,
            _job_id=f"telegram:clear-reply-markup:{event_id}",
        )
        if trace_id:
            _log_timing(
                trace_id=trace_id,
                stage="reply_markup_clear_enqueued",
                started_at=started_at,
                user_id=user_id,
                extra=f"message_id={message_id}",
            )
    except RuntimeError:
        await _clear_reply_markup_async(
            token=token,
            chat_id=chat_id,
            message_id=message_id,
            trace_id=trace_id,
            user_id=user_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to defer reply markup cleanup [user=%s message_id=%s]: %s",
            user_id,
            message_id,
            exc,
        )


async def _process_telegram_update_core(
    token: str,
    chat_id: Any,
    user_id: str,
    message_obj: Any,
    callback_query: Any,
    callback_query_id: Any,
    msg_obj: Any,
    process_message_uc: Any,
    trace_id: str,
) -> None:
    """Núcleo del procesamiento de actualizaciones de Telegram."""
    core_started_at = time.perf_counter()
    _log_timing(
        trace_id=trace_id,
        stage="background_core_start",
        started_at=core_started_at,
        user_id=user_id,
        extra=f"has_callback={bool(callback_query)} has_message={bool(message_obj)}",
    )
    fsm = TelegramConversationFSM(user_id=user_id, state_store=get_fsm_store())

    # Mapeo de entrada numérica a callback query simulado (soporte híbrido)
    if message_obj and not callback_query:
        message_text = message_obj.get("text")
        if message_text:
            stripped = message_text.strip()
            if stripped.isdigit():
                val = int(stripped)
                ctx = await fsm.get_context()
                options = ctx.get("_menu_options", [])
                if 1 <= val <= len(options):
                    selected_callback = options[val - 1]
                    current_fsm_version = await fsm.get_fsm_version()
                    callback_query = {
                        "id": f"num_{int(time.time() * 1000)}",
                        "from": message_obj.get("from"),
                        "message": message_obj,
                        "data": f"{selected_callback}#{current_fsm_version}",
                    }
                    callback_query_id = callback_query["id"]
                    msg_obj = message_obj
                    message_obj = None  # Descartamos procesamiento de mensaje libre

    # Chequeo de expiración por inactividad de 30 minutos (1800 segundos)
    ctx = await fsm.get_context()
    last_interaction = ctx.get("_last_interaction_at")
    if last_interaction is not None:
        if time.time() - last_interaction >= 1800:
            logger.info(
                "Session for user %s expired due to inactivity. Resetting FSM & LLM context.",
                user_id,
            )
            expiry_started_at = time.perf_counter()
            await fsm.reset()

            await _clear_latest_conversation_session(
                user_id=user_id,
                trace_id=trace_id,
                reason="expired_inactivity",
            )
            _log_timing(
                trace_id=trace_id,
                stage="expired_session_reset",
                started_at=expiry_started_at,
                user_id=user_id,
                extra="reason=expired_inactivity",
            )

            # Forzar el comportamiento de /start automático
            if callback_query:
                callback_query["data"] = "menu:back_to_main"
            elif message_obj:
                message_obj["text"] = "/start"

    if callback_query:
        # Es un click en el menú (InlineKeyboard)
        raw_callback_data = callback_query.get("data")
        if not raw_callback_data:
            return

        # Verificar estado del FSM para validar si se permite la acción del menú
        current_state = await fsm.get_state()
        active_menu_id = await fsm.get_active_menu_id()
        current_fsm_version = await fsm.get_fsm_version()

        # 2. Filtrado de Menú Expirado (Defensa en 3 Capas)
        is_valid = False
        btn_version = None

        # Intentar Capa 1: ID de Mensaje (solo si no es una selección numérica híbrida)
        is_numeric_selection = callback_query.get("id", "").startswith("num_")
        if active_menu_id is not None and msg_obj and not is_numeric_selection:
            is_valid = msg_obj.get("message_id") == active_menu_id
        else:
            # Capa 2: Contador de Versión/Turnos
            if "#" in raw_callback_data:
                try:
                    btn_version = int(raw_callback_data.split("#")[1])
                except ValueError:
                    pass

            if btn_version is not None:
                is_valid = btn_version == current_fsm_version
            else:
                # Capa 3: Validación Temporal (menos de 10 minutos) y Estado FSM
                import time as ttime

                msg_date = msg_obj.get("date", 0) if msg_obj else 0
                current_time = int(ttime.time())
                is_valid = (current_time - msg_date < 600) and (
                    current_state in {FSMState.IDLE, FSMState.IN_MENU}
                )

        if not is_valid:
            logger.warning(
                "Rejected expired callback [user=%s]: msg_id=%s (active=%s), btn_ver=%s (current=%s)",
                user_id,
                msg_obj.get("message_id") if msg_obj else None,
                active_menu_id,
                btn_version,
                current_fsm_version,
            )
            # Solución 2: Responder callback y limpiar reply markup en paralelo
            tasks = []
            if callback_query_id:
                from services.telegram_service import answer_telegram_callback_query

                tasks.append(
                    answer_telegram_callback_query(
                        bot_token=token,
                        callback_query_id=callback_query_id,
                        text="Este menú ha expirado o ya no está activo.",
                    )
                )
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if msg_obj and msg_obj.get("message_id"):
                await _defer_clear_reply_markup(
                    token=token,
                    chat_id=chat_id,
                    message_id=msg_obj["message_id"],
                    trace_id=trace_id,
                    user_id=user_id,
                )
            return

        # Si el click es válido, respondemos primero el callback para liberar la UI.
        tasks = []
        if callback_query_id:
            from services.telegram_service import answer_telegram_callback_query

            tasks.append(
                answer_telegram_callback_query(
                    bot_token=token, callback_query_id=callback_query_id
                )
            )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if msg_obj and msg_obj.get("message_id"):
            await _defer_clear_reply_markup(
                token=token,
                chat_id=chat_id,
                message_id=msg_obj["message_id"],
                trace_id=trace_id,
                user_id=user_id,
            )

        # Limpiar callback_data de la versión para el procesamiento de intents
        callback_data = raw_callback_data.split("#")[0]

        # Interceptar botones de navegación de categorías
        if callback_data == "menu:categorias":
            from config.database import SessionLocal
            from services.category_service import CategoryService

            db = SessionLocal()
            try:
                cat_svc = CategoryService(db)
                categories = cat_svc.list_categories()
                buttons = []
                idx = 1
                for i in range(0, len(categories), 2):
                    row = []
                    for cat in categories[i : i + 2]:
                        row.append(
                            {
                                "text": f"{idx}. 🏷️ {cat.name}",
                                "callback_data": f"cat_select:{cat.name}",
                            }
                        )
                        idx += 1
                    buttons.append(row)
                buttons.append(
                    [
                        {
                            "text": f"{idx}. 🔙 Menú Principal",
                            "callback_data": "menu:back_to_main",
                        }
                    ]
                )
                await send_menu_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text="Selecciona una categoría para ver los productos disponibles:",
                    reply_markup={"inline_keyboard": buttons},
                    fsm=fsm,
                    trace_id=trace_id,
                    user_id=user_id,
                )
            finally:
                db.close()
            return

        elif callback_data.startswith("cat_select:"):
            category_name = callback_data.split(":", 1)[1]
            from config.database import SessionLocal
            from models.product import Product

            db = SessionLocal()
            try:
                products = (
                    db.query(Product)
                    .filter(
                        Product.category == category_name,
                        Product.is_available.is_(True),
                    )
                    .all()
                )
                if not products:
                    response_text = f"No hay productos disponibles en la categoría '{category_name}' en este momento."
                else:
                    lines = [f"Productos en '{category_name}':"]
                    for p in products:
                        lines.append(
                            f"- {p.name}: ${float(p.price):,.0f} ({p.stock} un)"
                        )
                    response_text = "\n".join(lines)
                await send_menu_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text=response_text,
                    reply_markup={
                        "inline_keyboard": [
                            [
                                {
                                    "text": "1. Volver a Categorías 🏷️",
                                    "callback_data": "menu:categorias",
                                }
                            ],
                            [
                                {
                                    "text": "2. Menú Principal 🔙",
                                    "callback_data": "menu:back_to_main",
                                }
                            ],
                        ]
                    },
                    fsm=fsm,
                    trace_id=trace_id,
                    user_id=user_id,
                )
            finally:
                db.close()
            return

        elif callback_data == "menu:back_to_main":
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text="¿En qué puedo ayudarte hoy?",
                reply_markup=build_main_menu(_get_human_agent_available()),
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
            )
            return

        # Resolver FSM
        new_state, context = await fsm.transition(raw_callback_data)

        intent = context.get("intent")
        response_text = f"Has seleccionado una opción no implementada: {callback_data}"

        if intent == "consultar_stock":
            response_text = "Por favor, escribe el nombre del producto que buscas:"
        elif intent == "consultar_precio":
            response_text = (
                "Por favor, escribe el nombre del producto para consultar su precio:"
            )
        elif intent == "get_chatbot_info":
            response_text = "Nuestro horario de atención es de Lunes a Sábado de 10:00 a 22:00, y Domingo de 12:00 a 20:00."
        elif intent == "contactar_humano":
            response_text = "Un ejecutivo se pondrá en contacto contigo pronto. ¿En qué más puedo ayudarte?"

        await send_menu_message(
            bot_token=token,
            chat_id=chat_id,
            text=response_text,
            reply_markup=build_main_menu(_get_human_agent_available())
            if new_state == FSMState.IDLE
            else None,
            fsm=fsm,
            trace_id=trace_id,
            user_id=user_id,
        )
        _log_timing(
            trace_id=trace_id,
            stage="callback_flow_done",
            started_at=core_started_at,
            user_id=user_id,
            extra=f"intent={intent}",
        )
        return

    # Procesamiento de Mensajes de Texto
    message_text = message_obj.get("text")
    if not message_text:
        return

    current_state = await fsm.get_state()
    fsm_context = await fsm.get_context()

    # Interceptar comandos de reinicio / salida
    cmd_text = message_text.strip().lower()
    if cmd_text in {"/start", "/cancel", "/exit", "/salir", "/clear", "/reset"}:
        await fsm.reset()

        if cmd_text == "/start":
            start_command_at = time.perf_counter()
            welcome_text = (
                "¡Bienvenido! 🙂\n\n"
                "Negocio El Buen Trago.\n"
                "Horario: Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00.\n"
                "Servicios: Venta de licores, cervezas artesanales, vinos, pedidos a domicilio.\n"
                "Ubicación: Santiago, Chile.\n\n"
                "¿En qué puedo ayudarte hoy?"
            )
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text=welcome_text,
                reply_markup=build_main_menu(_get_human_agent_available()),
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
            )
            await _clear_latest_conversation_session(
                user_id=user_id,
                trace_id=trace_id,
                reason="start_command",
            )
            _log_timing(
                trace_id=trace_id,
                stage="start_command_responded",
                started_at=start_command_at,
                user_id=user_id,
            )
        else:
            reset_command_at = time.perf_counter()
            await send_menu_message(
                bot_token=token,
                chat_id=chat_id,
                text="Sesión conversacional reiniciada y limpia. Tu carro de compra sigue conservado intacto. ¿En qué puedo ayudarte hoy?",
                reply_markup=build_main_menu(_get_human_agent_available()),
                fsm=fsm,
                trace_id=trace_id,
                user_id=user_id,
            )
            await _clear_latest_conversation_session(
                user_id=user_id,
                trace_id=trace_id,
                reason=f"reset_command:{cmd_text}",
            )
            _log_timing(
                trace_id=trace_id,
                stage="reset_command_responded",
                started_at=reset_command_at,
                user_id=user_id,
                extra=f"command={cmd_text}",
            )
        return

    # Si estamos esperando algo específico (ej: producto), podemos prefijar el texto
    if current_state == FSMState.AWAITING_PRODUCT_NAME:
        intent = fsm_context.get("intent")
        if intent == "consultar_stock":
            message_text = f"¿Tienen stock de {message_text}?"
        elif intent == "consultar_precio":
            message_text = f"¿Cuál es el precio de {message_text}?"
        await fsm.reset()  # Volver a IDLE tras procesar

    # Delega la lógica de negocio al Use Case
    cmd = ProcessMessageCommand(
        user_id=user_id,
        platform="telegram",
        message=message_text,
    )

    try:
        use_case_started_at = time.perf_counter()
        result = await process_message_uc.execute(cmd)
        response_text = result.response
        _log_timing(
            trace_id=trace_id,
            stage="process_message_uc_done",
            started_at=use_case_started_at,
            user_id=user_id,
            extra=f"response_empty={not bool(response_text)}",
        )
    except Exception as e:
        logger.error("Error processing telegram message: %s", e)
        response_text = "Ocurrió un error al procesar tu solicitud. Intenta nuevamente."

    # Si la respuesta es vacía, significa que el bot está pausado (Human Takeover activo)
    if not response_text:
        return

    # Enviar respuesta con el menú principal siempre activo si estamos en IDLE
    current_state = await fsm.get_state()
    await send_menu_message(
        bot_token=token,
        chat_id=chat_id,
        text=response_text,
        reply_markup=build_main_menu(_get_human_agent_available())
        if current_state == FSMState.IDLE
        else None,
        fsm=fsm,
        trace_id=trace_id,
        user_id=user_id,
    )
    _log_timing(
        trace_id=trace_id,
        stage="text_message_done",
        started_at=core_started_at,
        user_id=user_id,
    )


async def process_telegram_update_background(
    token: str,
    chat_id: Any,
    user_id: str,
    message_obj: Any,
    callback_query: Any,
    callback_query_id: Any,
    msg_obj: Any,
    process_message_uc: Any,
    lock_key: str,
    lock_acquired: bool,
    redis_client: Any,
    trace_id: str,
) -> None:
    """Manejador en segundo plano para procesar la actualización y liberar el lock."""
    background_started_at = time.perf_counter()
    try:
        await _process_telegram_update_core(
            token=token,
            chat_id=chat_id,
            user_id=user_id,
            message_obj=message_obj,
            callback_query=callback_query,
            callback_query_id=callback_query_id,
            msg_obj=msg_obj,
            process_message_uc=process_message_uc,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error("Error in background telegram processing: %s", e)
    finally:
        if lock_acquired:
            if redis_client is not None:
                try:
                    await redis_client.delete(lock_key)
                except Exception as e:
                    logger.error(
                        "Failed to release Redis lock in background task: %s", e
                    )
            else:
                _local_locks.discard(user_id)
        _log_timing(
            trace_id=trace_id,
            stage="background_task_finished",
            started_at=background_started_at,
            user_id=user_id,
        )


@router.post("/webhook/{token}")
async def telegram_webhook(
    token: str,
    request: Request,
    process_message_uc: ProcessMessageUCDep,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Recibe updates de Telegram, valida el webhook y agenda su procesamiento asíncrono."""
    webhook_started_at = time.perf_counter()
    if token != settings.telegram_bot_token:
        logger.warning("Unauthorized webhook request with token: %s", token)
        raise HTTPException(403, "Forbidden: Invalid Telegram bot token")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error("Failed to parse Telegram payload: %s", e)
        raise HTTPException(400, "Invalid JSON payload")

    # Detectar tipo de update: Mensaje o Callback Query
    message_obj = payload.get("message") or payload.get("edited_message")
    callback_query = payload.get("callback_query")

    if not message_obj and not callback_query:
        return {"status": "ok", "detail": "no message or callback in payload"}

    # Resolver chat_id y user_id de forma unificada
    chat_id = None
    user_id = None
    callback_query_id = None
    msg_obj = None
    if callback_query:
        from_obj = callback_query.get("from")
        msg_obj = callback_query.get("message")
        chat_id = msg_obj.get("chat", {}).get("id") if msg_obj else None
        user_id = str(from_obj.get("id")) if from_obj else str(chat_id)
        callback_query_id = callback_query.get("id")
    else:
        chat_obj = message_obj.get("chat")
        from_obj = message_obj.get("from")
        chat_id = chat_obj.get("id") if chat_obj else None
        user_id = str(from_obj.get("id") if from_obj else chat_id)

    if not user_id or not chat_id:
        return {"status": "ok", "detail": "invalid user_id or chat_id"}

    update_kind = "callback" if callback_query else "message"
    raw_update_id = payload.get("update_id")
    trace_id = (
        f"tg:{user_id}:{raw_update_id}"
        if raw_update_id is not None
        else f"tg:{user_id}:{int(time.time() * 1000)}"
    )
    _log_timing(
        trace_id=trace_id,
        stage="webhook_parsed",
        started_at=webhook_started_at,
        user_id=user_id,
        extra=f"kind={update_kind}",
    )

    # 1. Concurrency Lock: block concurrent requests from the same user_id (adquirido síncronamente)
    lock_key = f"lock:telegram:user:{user_id}"
    redis_client = get_redis_client()
    lock_acquired = False

    if redis_client is not None:
        try:
            lock_acquired = await redis_client.set(lock_key, "locked", ex=20, nx=True)
            if not lock_acquired:
                logger.warning(
                    "Concurrency warning: duplicate request from user %s blocked",
                    user_id,
                )
                if callback_query:
                    callback_query_id = callback_query.get("id")
                    if callback_query_id:
                        from services.telegram_service import (
                            answer_telegram_callback_query,
                        )

                        background_tasks.add_task(
                            answer_telegram_callback_query,
                            bot_token=token,
                            callback_query_id=callback_query_id,
                            text="Procesando tu solicitud anterior, por favor espera...",
                        )
                        _log_timing(
                            trace_id=trace_id,
                            stage="duplicate_callback_deferred",
                            started_at=webhook_started_at,
                            user_id=user_id,
                        )
                return {"status": "ok", "detail": "duplicate request blocked"}
        except Exception as e:
            logger.error("Redis concurrency lock error: %s", e)
    else:
        if user_id in _local_locks:
            logger.warning(
                "Local concurrency warning: duplicate request from user %s blocked",
                user_id,
            )
            if callback_query:
                callback_query_id = callback_query.get("id")
                if callback_query_id:
                    from services.telegram_service import answer_telegram_callback_query

                    background_tasks.add_task(
                        answer_telegram_callback_query,
                        bot_token=token,
                        callback_query_id=callback_query_id,
                        text="Procesando tu solicitud anterior, por favor espera...",
                    )
                    _log_timing(
                        trace_id=trace_id,
                        stage="duplicate_callback_deferred",
                        started_at=webhook_started_at,
                        user_id=user_id,
                    )
            return {"status": "ok", "detail": "duplicate request blocked"}
        _local_locks.add(user_id)
        lock_acquired = True

    # 2. Programar ejecución en segundo plano y responder de inmediato
    background_tasks.add_task(
        process_telegram_update_background,
        token=token,
        chat_id=chat_id,
        user_id=user_id,
        message_obj=message_obj,
        callback_query=callback_query,
        callback_query_id=callback_query_id,
        msg_obj=msg_obj if callback_query else None,
        process_message_uc=process_message_uc,
        lock_key=lock_key,
        lock_acquired=lock_acquired,
        redis_client=redis_client,
        trace_id=trace_id,
    )

    _log_timing(
        trace_id=trace_id,
        stage="webhook_scheduled",
        started_at=webhook_started_at,
        user_id=user_id,
        extra=f"lock_acquired={lock_acquired} kind={update_kind}",
    )

    return {"status": "ok", "detail": "scheduled"}
