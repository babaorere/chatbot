"""
telegram_controller — Webhook handler para Telegram.

Recibe actualizaciones de Telegram, resuelve el FSM (menús vs texto libre),
y delega la inferencia y reglas de negocio a ProcessMessageUseCase.
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, Request, HTTPException

from app.container import ProcessMessageUCDep, get_redis_client
from application.use_cases.commands import ProcessMessageCommand
from infrastructure.channels.telegram_fsm import (
    TelegramConversationFSM,
    FSMStateStore,
    FSMState,
    RedisFSMStateStore,
)
from config.settings import settings
from services.telegram_service import send_telegram_message, build_main_menu, inject_version_to_reply_markup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

_memory_fsm_store = FSMStateStore()

# Cerradura local en memoria para concurrencia si Redis no está activo
_local_locks: set[str] = set()


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
) -> int | None:
    """Wrapper para enviar mensajes. Si contiene reply_markup, inyecta la versión del FSM

    e incrementa el contador, guardando el message_id resultante como el menú activo.
    """
    if reply_markup and "inline_keyboard" in reply_markup:
        version = await fsm.increment_fsm_version()
        reply_markup = inject_version_to_reply_markup(reply_markup, version)

    msg_id = await send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
    )

    if msg_id and reply_markup and "inline_keyboard" in reply_markup:
        await fsm.set_active_menu_id(msg_id)

    return msg_id


def _get_human_agent_available() -> bool:
    """Retrieves whether a human agent is currently available from business configuration."""
    from config.database import SessionLocal
    from services.business_config_service import BusinessConfigService
    db = SessionLocal()
    try:
        cfg_svc = BusinessConfigService(db)
        cfg = cfg_svc.get_config()
        return cfg.human_agent_available if cfg else True
    except Exception:
        return True
    finally:
        db.close()


@router.post("/webhook/{token}")
async def telegram_webhook(
    token: str,
    request: Request,
    process_message_uc: ProcessMessageUCDep,
) -> dict[str, Any]:
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

    # Resolver chat_id y user_id de forma unificada para el lock de concurrencia
    chat_id = None
    user_id = None
    if callback_query:
        from_obj = callback_query.get("from")
        msg_obj = callback_query.get("message")
        chat_id = msg_obj.get("chat", {}).get("id") if msg_obj else None
        user_id = str(from_obj.get("id")) if from_obj else str(chat_id)
    else:
        chat_obj = message_obj.get("chat")
        from_obj = message_obj.get("from")
        chat_id = chat_obj.get("id") if chat_obj else None
        user_id = str(from_obj.get("id") if from_obj else chat_id)

    if not user_id or not chat_id:
        return {"status": "ok", "detail": "invalid user_id or chat_id"}

    # 1. Concurrency Lock: block concurrent requests from the same user_id
    lock_key = f"lock:telegram:user:{user_id}"
    redis_client = get_redis_client()
    lock_acquired = False

    if redis_client is not None:
        try:
            lock_acquired = await redis_client.set(lock_key, "locked", ex=10, nx=True)
            if not lock_acquired:
                logger.warning("Concurrency warning: duplicate request from user %s blocked", user_id)
                if callback_query:
                    callback_query_id = callback_query.get("id")
                    if callback_query_id:
                        from services.telegram_service import answer_telegram_callback_query
                        await answer_telegram_callback_query(
                            bot_token=token,
                            callback_query_id=callback_query_id,
                            text="Procesando tu solicitud anterior, por favor espera...",
                        )
                return {"status": "ok", "detail": "duplicate request blocked"}
        except Exception as e:
            logger.error("Redis concurrency lock error: %s", e)
    else:
        if user_id in _local_locks:
            logger.warning("Local concurrency warning: duplicate request from user %s blocked", user_id)
            if callback_query:
                callback_query_id = callback_query.get("id")
                if callback_query_id:
                    from services.telegram_service import answer_telegram_callback_query
                    await answer_telegram_callback_query(
                        bot_token=token,
                        callback_query_id=callback_query_id,
                        text="Procesando tu solicitud anterior, por favor espera...",
                    )
            return {"status": "ok", "detail": "duplicate request blocked"}
        _local_locks.add(user_id)
        lock_acquired = True

    try:
        if callback_query:
            # Es un click en el menú (InlineKeyboard)
            raw_callback_data = callback_query.get("data")
            callback_query_id = callback_query.get("id")

            if not raw_callback_data:
                return {"status": "ok", "detail": "invalid callback"}

            # Verificar estado del FSM para validar si se permite la acción del menú
            fsm = TelegramConversationFSM(user_id=user_id, state_store=get_fsm_store())
            current_state = await fsm.get_state()
            active_menu_id = await fsm.get_active_menu_id()
            current_fsm_version = await fsm.get_fsm_version()
            msg_obj = callback_query.get("message")

            # 2. Filtrado de Menú Expirado (Defensa en 3 Capas)
            is_valid = False
            btn_version = None

            # Intentar Capa 1: ID de Mensaje
            if active_menu_id is not None and msg_obj:
                is_valid = (msg_obj.get("message_id") == active_menu_id)
            else:
                # Capa 2: Contador de Versión/Turnos
                if "#" in raw_callback_data:
                    try:
                        btn_version = int(raw_callback_data.split("#")[1])
                    except ValueError:
                        pass

                if btn_version is not None:
                    is_valid = (btn_version == current_fsm_version)
                else:
                    # Capa 3: Validación Temporal (menos de 1 hora) y Estado FSM
                    import time
                    msg_date = msg_obj.get("date", 0) if msg_obj else 0
                    current_time = int(time.time())
                    is_valid = (current_time - msg_date < 3600) and (
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
                if callback_query_id:
                    from services.telegram_service import answer_telegram_callback_query
                    await answer_telegram_callback_query(
                        bot_token=token,
                        callback_query_id=callback_query_id,
                        text="Este menú ha expirado o ya no está activo.",
                    )
                if msg_obj and msg_obj.get("message_id"):
                    from services.telegram_service import clear_telegram_reply_markup
                    await clear_telegram_reply_markup(
                        bot_token=token,
                        chat_id=chat_id,
                        message_id=msg_obj["message_id"],
                    )
                return {"status": "ok"}

            # Si el click es válido, respondemos el callback query y removemos el teclado inline para deshabilitarlo (UI fallback)
            if callback_query_id:
                from services.telegram_service import answer_telegram_callback_query
                await answer_telegram_callback_query(bot_token=token, callback_query_id=callback_query_id)

            if msg_obj and msg_obj.get("message_id"):
                from services.telegram_service import clear_telegram_reply_markup
                await clear_telegram_reply_markup(
                    bot_token=token,
                    chat_id=chat_id,
                    message_id=msg_obj["message_id"],
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
                    for i in range(0, len(categories), 2):
                        row = []
                        for cat in categories[i:i+2]:
                            row.append(
                                {"text": f"🏷️ {cat.name}", "callback_data": f"cat_select:{cat.name}"}
                            )
                        buttons.append(row)
                    buttons.append([{"text": "🔙 Menú Principal", "callback_data": "menu:back_to_main"}])
                    await send_menu_message(
                        bot_token=token,
                        chat_id=chat_id,
                        text="Selecciona una categoría para ver los productos disponibles:",
                        reply_markup={"inline_keyboard": buttons},
                        fsm=fsm,
                    )
                finally:
                    db.close()
                return {"status": "ok"}

            elif callback_data.startswith("cat_select:"):
                category_name = callback_data.split(":", 1)[1]
                from config.database import SessionLocal
                from models.product import Product
                db = SessionLocal()
                try:
                    products = (
                        db.query(Product)
                        .filter(Product.category == category_name, Product.is_available.is_(True))
                        .all()
                    )
                    if not products:
                        response_text = f"No hay productos disponibles en la categoría '{category_name}' en este momento."
                    else:
                        lines = [f"Productos en '{category_name}':"]
                        for p in products:
                            lines.append(f"- {p.name}: ${float(p.price):,.0f} ({p.stock} un)")
                        response_text = "\n".join(lines)
                    await send_menu_message(
                        bot_token=token,
                        chat_id=chat_id,
                        text=response_text,
                        reply_markup={
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "Volver a Categorías 🏷️",
                                        "callback_data": "menu:categorias",
                                    }
                                ],
                                [
                                    {
                                        "text": "Menú Principal 🔙",
                                        "callback_data": "menu:back_to_main",
                                    }
                                ],
                            ]
                        },
                        fsm=fsm,
                    )
                finally:
                    db.close()
                return {"status": "ok"}

            elif callback_data == "menu:back_to_main":
                await send_menu_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text="¿En qué puedo ayudarte hoy?",
                    reply_markup=build_main_menu(_get_human_agent_available()),
                    fsm=fsm,
                )
                return {"status": "ok"}

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
            )
            return {"status": "ok"}

        # Procesamiento de Mensajes de Texto
        message_text = message_obj.get("text")
        if not message_text:
            return {"status": "ok", "detail": "no message text"}

        # Revisar estado actual del FSM
        fsm = TelegramConversationFSM(user_id=user_id, state_store=get_fsm_store())
        current_state = await fsm.get_state()
        fsm_context = await fsm.get_context()

        # Interceptar comandos de reinicio / salida
        cmd_text = message_text.strip().lower()
        if cmd_text in {"/start", "/cancel", "/exit", "/salir", "/clear", "/reset"}:
            await fsm.reset()

            # Obtener el session_id más reciente de la base de datos
            from config.database import SessionLocal
            from services.user_service import UserService
            from services.conversation_service import ConversationService
            db = SessionLocal()
            try:
                u_svc = UserService(db)
                user = u_svc.get_or_create(external_id=user_id, platform="telegram")
                conv_svc = ConversationService(db)
                conversations = conv_svc.get_by_user_id(user.id)
                session_id = conversations[0].session_id if conversations else str(uuid.uuid4())
            finally:
                db.close()

            await process_message_uc.clear_session(user_id=user_id, session_id=session_id)

            if cmd_text == "/start":
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
                )
            else:
                await send_menu_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text="Sesión conversacional reiniciada y limpia. Tu carro de compra sigue conservado intacto. ¿En qué puedo ayudarte hoy?",
                    reply_markup=build_main_menu(_get_human_agent_available()),
                    fsm=fsm,
                )
            return {"status": "ok"}

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
            result = await process_message_uc.execute(cmd)
            response_text = result.response
        except Exception as e:
            logger.error("Error processing telegram message: %s", e)
            response_text = "Ocurrió un error al procesar tu solicitud. Intenta nuevamente."

        # Si la respuesta es vacía, significa que el bot está pausado (Human Takeover activo)
        if not response_text:
            return {"status": "ok"}

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
        )

        return {"status": "ok"}

    finally:
        if lock_acquired:
            if redis_client is not None:
                try:
                    await redis_client.delete(lock_key)
                except Exception as e:
                    logger.error("Failed to release Redis lock: %s", e)
            else:
                _local_locks.discard(user_id)
