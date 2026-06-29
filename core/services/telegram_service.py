from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def send_telegram_message(
    bot_token: str, chat_id: str | int, text: str, reply_markup: dict | None = None
) -> int | None:
    """Envía un mensaje de texto a un chat de Telegram usando httpx de forma asíncrona.

    Retorna el message_id si tiene éxito, o None si falla.
    """
    if not bot_token or not chat_id:
        logger.warning(
            "Telegram credentials missing. Cannot send message. Token: %s, ChatId: %s",
            "OK" if bot_token else "MISSING",
            "OK" if chat_id else "MISSING",
        )
        return None

    try:
        from app.container import get_http_client
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        client = get_http_client()
        resp = await client.post(url, json=payload)
        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("Message successfully sent to Telegram chat: %s", chat_id)
            return resp.json().get("result", {}).get("message_id")
        else:
            logger.error("Telegram API returned failure: %s", resp.text)
            return None
    except Exception as e:
        logger.error("Failed to send Telegram message to chat %s: %s", chat_id, e)
        return None


def inject_version_to_reply_markup(reply_markup: dict | None, version: int) -> dict | None:
    """Sufija la versión del FSM al callback_data de todos los botones inline."""
    if not reply_markup or "inline_keyboard" not in reply_markup:
        return reply_markup

    new_keyboard = []
    for row in reply_markup["inline_keyboard"]:
        new_row = []
        for btn in row:
            new_btn = btn.copy()
            if "callback_data" in new_btn:
                cb = new_btn["callback_data"]
                base = cb.split("#")[0]
                new_btn["callback_data"] = f"{base}#{version}"
            new_row.append(new_btn)
        new_keyboard.append(new_row)

    return {"inline_keyboard": new_keyboard}


def build_main_menu(human_agent_available: bool = True) -> dict:
    """Construye el menú principal de Telegram."""
    buttons = [
        [
            {"text": "🏷️ Ver Categorías", "callback_data": "menu:categorias"},
            {"text": "📦 Consultar Stock", "callback_data": "menu:stock"},
        ],
        [
            {"text": "💰 Ver Precios", "callback_data": "menu:precio"},
            {"text": "🕒 Horarios", "callback_data": "menu:horario"},
        ]
    ]
    if human_agent_available:
        buttons.append([
            {"text": "👤 Hablar con Humano", "callback_data": "menu:contacto"},
        ])
    return {
        "inline_keyboard": buttons
    }


async def clear_telegram_reply_markup(
    bot_token: str, chat_id: str | int, message_id: int
) -> bool:
    """Elimina los botones inline (reply_markup) de un mensaje específico para inhabilitarlo."""
    if not bot_token or not chat_id or not message_id:
        return False
    try:
        from app.container import get_http_client
        url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": None,
        }
        client = get_http_client()
        resp = await client.post(url, json=payload)
        return resp.status_code == 200 and resp.json().get("ok")
    except Exception as e:
        logger.error("Failed to clear Telegram reply markup for msg %s: %s", message_id, e)
        return False


async def answer_telegram_callback_query(
    bot_token: str, callback_query_id: str, text: str | None = None
) -> bool:
    """Confirma un callback query para evitar que quede cargando en el cliente de Telegram."""
    if not bot_token or not callback_query_id:
        return False
    try:
        from app.container import get_http_client
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
        }
        if text:
            payload["text"] = text
        client = get_http_client()
        resp = await client.post(url, json=payload)
        return resp.status_code == 200 and resp.json().get("ok")
    except Exception as e:
        logger.error("Failed to answer callback query %s: %s", callback_query_id, e)
        return False
