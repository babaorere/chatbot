"""
IChannelHandler — Port (Protocol) para canales de entrada/salida de mensajes.

Abstrae el canal de comunicación (Telegram, REST, WhatsApp, etc.) para que
el use case de procesamiento de mensajes sea agnóstico al canal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class InputRoute(Enum):
    """Tipo de enrutado del input recibido."""

    LLM_INFERENCE = "llm_inference"
    """El texto llega libre — debe procesarse por el LLM."""

    MENU_ACTION = "menu_action"
    """El usuario seleccionó una opción de menú (callback_query)."""

    FSM_EXPECTED_INPUT = "fsm_expected_input"
    """El FSM está esperando un input específico del usuario (ej: nombre del producto)."""


@dataclass(frozen=True)
class ChannelMessage:
    """Mensaje normalizado proveniente de cualquier canal."""

    user_id: str
    """Identificador único del usuario en el canal."""

    chat_id: str
    """Identificador del chat/conversación en el canal."""

    text: str
    """Texto del mensaje (vacío si es un callback puro)."""

    platform: str
    """Nombre del canal: 'telegram', 'rest', 'whatsapp', etc."""

    channel_identifier: str
    """Token/identificador del canal (ej: bot token de Telegram)."""

    is_callback: bool = False
    """True si el mensaje proviene de una selección de menú (callback_query)."""

    callback_data: str | None = None
    """Dato del callback si is_callback=True."""

    raw_payload: dict[str, Any] = field(default_factory=dict)
    """Payload original sin procesar, para uso avanzado."""


@dataclass
class MenuButton:
    """Botón individual de un menú."""

    label: str
    """Texto visible en el botón."""

    callback_data: str
    """Dato que se enviará al presionar el botón."""


@dataclass
class ChannelMenu:
    """Menú de opciones a presentar al usuario."""

    buttons: list[list[MenuButton]]
    """Filas de botones. Cada lista interna es una fila."""

    inline: bool = True
    """True = InlineKeyboard (sobre el mensaje). False = ReplyKeyboard (teclado)."""


@runtime_checkable
class IChannelHandler(Protocol):
    """Contrato para canales de entrada/salida de mensajes."""

    async def parse_input(self, raw_payload: dict[str, Any]) -> ChannelMessage | None:
        """Convierte el payload raw del canal en un ChannelMessage normalizado.

        Args:
            raw_payload: Payload JSON recibido del canal (ej: update de Telegram).

        Returns:
            ChannelMessage normalizado, o None si el payload no contiene
            un mensaje procesable (ej: evento sin texto).
        """
        ...

    async def send_message(
        self,
        chat_id: str,
        text: str,
        menu: ChannelMenu | None = None,
    ) -> None:
        """Envía un mensaje de texto al usuario, opcionalmente con menú.

        Args:
            chat_id: Identificador del chat destino en el canal.
            text: Texto del mensaje a enviar.
            menu: Menú de botones opcional a presentar junto con el mensaje.
        """
        ...

    def route_input(self, message: ChannelMessage) -> InputRoute:
        """Determina cómo debe procesarse el input recibido.

        Args:
            message: Mensaje normalizado del canal.

        Returns:
            InputRoute indicando si el input debe ir al LLM, al FSM, o a un menú.
        """
        ...
