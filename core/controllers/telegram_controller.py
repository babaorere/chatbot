"""
telegram_controller — Webhook handler para Telegram.

Recibe actualizaciones de Telegram, resuelve el FSM (menús vs texto libre),
y delega la inferencia y reglas de negocio a ProcessMessageUseCase.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, HTTPException

from app.container import ProcessMessageUCDep
from application.use_cases.commands import ProcessMessageCommand
from infrastructure.channels.telegram_fsm import TelegramConversationFSM, FSMStateStore, FSMState
from services.telegram_service import send_telegram_message, build_main_menu

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Instancia global en memoria para el FSM store (en prod debería ser RedisFSMStateStore)
_fsm_store = FSMStateStore()

@router.post("/webhook/{token}")
async def telegram_webhook(
    token: str,
    request: Request,
    process_message_uc: ProcessMessageUCDep,
) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("Failed to parse Telegram payload: %s", e)
        raise HTTPException(400, "Invalid JSON payload")

    # Detectar tipo de update: Mensaje o Callback Query
    message_obj = payload.get("message") or payload.get("edited_message")
    callback_query = payload.get("callback_query")

    if callback_query:
        # Es un click en el menú (InlineKeyboard)
        from_obj = callback_query.get("from")
        message_obj = callback_query.get("message")
        chat_id = message_obj.get("chat", {}).get("id") if message_obj else None
        user_id = str(from_obj.get("id")) if from_obj else str(chat_id)
        callback_data = callback_query.get("data")

        if not chat_id or not callback_data:
            return {"status": "ok", "detail": "invalid callback"}

        # Resolver FSM
        fsm = TelegramConversationFSM(user_id=user_id, state_store=_fsm_store)
        new_state, context = await fsm.transition(callback_data)

        intent = context.get("intent")
        response_text = f"Has seleccionado una opción no implementada: {callback_data}"

        if intent == "consultar_stock":
            response_text = "Por favor, escribe el nombre del producto que buscas:"
        elif intent == "consultar_precio":
            response_text = "Por favor, escribe el nombre del producto para consultar su precio:"
        elif intent == "get_botilleria_info":
            response_text = "Nuestro horario de atención es de Lunes a Sábado de 10:00 a 22:00, y Domingo de 12:00 a 20:00."
        elif intent == "contactar_humano":
            response_text = "Un ejecutivo se pondrá en contacto contigo pronto. ¿En qué más puedo ayudarte?"

        await send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=response_text,
            reply_markup=build_main_menu() if new_state == FSMState.IDLE else None,
        )
        return {"status": "ok"}

    if not message_obj:
        return {"status": "ok", "detail": "no message in payload"}

    chat_obj = message_obj.get("chat")
    from_obj = message_obj.get("from")
    message_text = message_obj.get("text")

    if not message_text or not chat_obj:
        return {"status": "ok", "detail": "no message text or chat"}

    chat_id = chat_obj.get("id")
    user_id = str(from_obj.get("id") if from_obj else chat_id)

    # Revisar estado actual del FSM
    fsm = TelegramConversationFSM(user_id=user_id, state_store=_fsm_store)
    current_state = await fsm.get_state()
    fsm_context = await fsm.get_context()

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
        channel_identifier=token,
        message=message_text,
    )

    try:
        result = await process_message_uc.execute(cmd)
        response_text = result.response
    except Exception as e:
        logger.error("Error processing telegram message: %s", e)
        response_text = "Ocurrió un error al procesar tu solicitud. Intenta nuevamente."

    # Enviar respuesta con el menú principal siempre activo si estamos en IDLE
    current_state = await fsm.get_state()
    await send_telegram_message(
        bot_token=token,
        chat_id=chat_id,
        text=response_text,
        reply_markup=build_main_menu() if current_state == FSMState.IDLE else None,
    )

    return {"status": "ok"}
