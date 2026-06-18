from __future__ import annotations

import logging
import httpx

logger = logging.getLogger(__name__)


async def send_telegram_message(
    bot_token: str, chat_id: str | int, text: str, reply_markup: dict | None = None
) -> bool:
    """Envía un mensaje de texto a un chat de Telegram usando httpx de forma asíncrona."""
    if not bot_token or not chat_id:
        logger.warning(
            "Telegram credentials missing. Cannot send message. Token: %s, ChatId: %s",
            "OK" if bot_token else "MISSING",
            "OK" if chat_id else "MISSING",
        )
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200 and resp.json().get("ok"):
                logger.info("Message successfully sent to Telegram chat: %s", chat_id)
                return True
            else:
                logger.error("Telegram API returned failure: %s", resp.text)
                return False
    except Exception as e:
        logger.error("Failed to send Telegram message to chat %s: %s", chat_id, e)
        return False


def build_main_menu() -> dict:
    """Construye el menú principal de Telegram."""
    return {
        "inline_keyboard": [
            [
                {"text": "📦 Consultar Stock", "callback_data": "menu:stock"},
                {"text": "💰 Ver Precios", "callback_data": "menu:precio"},
            ],
            [
                {"text": "🕒 Horarios", "callback_data": "menu:horario"},
                {"text": "👤 Hablar con Humano", "callback_data": "menu:contacto"},
            ],
        ]
    }
