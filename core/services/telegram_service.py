from __future__ import annotations

import logging
import time

from app.container import get_http_client

logger = logging.getLogger(__name__)


async def send_telegram_message(
    bot_token: str,
    chat_id: str | int,
    text: str,
    reply_markup: dict | None = None,
    trace_id: str | None = None,
) -> int:
    """Envía un mensaje de texto a un chat de Telegram usando httpx de forma asíncrona.

    Retorna el message_id si tiene éxito. Si falla, lanza una excepción explícita.
    """
    if not bot_token or not chat_id:
        raise ValueError(
            "Telegram credentials missing. Cannot send message "
            f"[token={'OK' if bot_token else 'MISSING'}, chat_id={'OK' if chat_id else 'MISSING'}]."
        )

    try:
        started_at = time.perf_counter()

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
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Message successfully sent to Telegram chat: %s%s elapsed_ms=%.2f",
                chat_id,
                f" trace={trace_id}" if trace_id else "",
                elapsed_ms,
            )
            return resp.json().get("result", {}).get("message_id")
        raise RuntimeError(f"Telegram API returned failure: {resp.text}")
    except Exception as e:
        logger.exception("Failed to send Telegram message to chat %s", chat_id)
        raise RuntimeError(f"Failed to send Telegram message to chat {chat_id}") from e


def extract_checkout_customer_message(payload: dict) -> str | None:
    """Extrae el texto oficial de confirmación de compra desde una respuesta de checkout."""
    message = payload.get("customer_message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return None


async def send_checkout_confirmation_message(
    bot_token: str,
    chat_id: str | int,
    checkout_payload: dict,
    trace_id: str | None = None,
) -> int | None:
    """Envía al cliente la confirmación de compra generada por el checkout."""
    message = extract_checkout_customer_message(checkout_payload)
    if not message:
        raise ValueError("checkout_payload must include a non-empty customer_message")
    return await send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=message,
        trace_id=trace_id,
    )


def inject_version_to_reply_markup(
    reply_markup: dict | None, version: int
) -> dict | None:
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


def build_main_menu(human_agent_available: bool = False) -> dict:
    """Construye el menú principal de Telegram."""
    buttons = [
        [
            {"text": "1. 🏷️ Ver Categorías", "callback_data": "menu:categorias"},
            {"text": "2. ✨ Promociones", "callback_data": "menu:promociones"},
        ],
        [
            {"text": "3. 🔥 Más vendidos", "callback_data": "menu:mas_vendidos"},
            {"text": "4. 🛒 Ver carrito", "callback_data": "menu:carrito"},
        ],
    ]
    if human_agent_available:
        buttons.append(
            [
                {"text": "5. 👤 Hablar con Humano", "callback_data": "menu:contacto"},
            ]
        )
    return {"inline_keyboard": buttons}


async def clear_telegram_reply_markup(
    bot_token: str, chat_id: str | int, message_id: int
) -> bool:
    """Elimina los botones inline (reply_markup) de un mensaje específico para inhabilitarlo."""
    if not bot_token or not chat_id or not message_id:
        raise ValueError(
            "Telegram credentials missing. Cannot clear reply markup "
            f"[token={'OK' if bot_token else 'MISSING'}, chat_id={'OK' if chat_id else 'MISSING'}, message_id={'OK' if message_id else 'MISSING'}]."
        )
    try:
        url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": None,
        }
        client = get_http_client()
        resp = await client.post(url, json=payload)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        raise RuntimeError(f"Telegram API returned failure: {resp.text}")
    except Exception as e:
        logger.exception(
            "Failed to clear Telegram reply markup for msg %s", message_id
        )
        raise RuntimeError(
            f"Failed to clear Telegram reply markup for msg {message_id}"
        ) from e


async def answer_telegram_callback_query(
    bot_token: str, callback_query_id: str, text: str | None = None
) -> bool:
    """Confirma un callback query para evitar que quede cargando en el cliente de Telegram."""
    if not bot_token or not callback_query_id:
        raise ValueError(
            "Telegram credentials missing. Cannot answer callback query "
            f"[token={'OK' if bot_token else 'MISSING'}, callback_query_id={'OK' if callback_query_id else 'MISSING'}]."
        )
    try:
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
        }
        if text:
            payload["text"] = text
        client = get_http_client()
        resp = await client.post(url, json=payload)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        raise RuntimeError(f"Telegram API returned failure: {resp.text}")
    except Exception as e:
        logger.exception("Failed to answer callback query %s", callback_query_id)
        raise RuntimeError(
            f"Failed to answer callback query {callback_query_id}"
        ) from e
