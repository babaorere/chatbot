from __future__ import annotations

import datetime
import os
import time
from typing import Any, cast
from zoneinfo import ZoneInfo

from google.adk import Agent, Runner
from google.adk.models.lite_llm import LiteLlm

from services.session_service_factory import create_session_service
from .constants import GADK_APP_NAME, GADK_INSTRUCTION, GADK_MODEL


# ============================================================================
# TOOLS — Funciones que el agente puede llamar
# ============================================================================


def get_current_datetime(query: str | None = None) -> str:
    """Obtiene la fecha y hora actual en Chile (zona horaria America/Santiago).

    Invoca esta herramienta cuando el usuario pregunte explícitamente por la
    fecha, hora, día de la semana, o cuando necesites contextualizar una
    respuesta con información temporal (ej: 'están abiertos ahora?', 'qué día
    es hoy?', 'es de noche?'). NO la invoques si el mensaje del usuario no
    tiene ninguna referencia temporal ni la respuesta la requiere.

    Args:
        query: Texto opcional con la consulta del usuario relacionada con
            tiempo (ej: 'qué hora es', 'es viernes?'). Puede ser None si
            el contexto ya indica que se necesita la hora actual sin una
            pregunta explícita.

    Returns:
        str: Cadena con el día de la semana, fecha completa (DD/MM/YYYY),
            hora actual (HH:MM) y zona horaria. Formato ejemplo:
            'Fecha/hora actual: Viernes 21/05/2026 14:30 (hora Chile)'.
    """
    tz = ZoneInfo("America/Santiago")
    now = datetime.datetime.now(tz)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    return f"Fecha/hora actual: {dias[now.weekday()]} {now.strftime('%d/%m/%Y %H:%M')} (hora Chile)"


def get_botilleria_info(query: str | None = None) -> str:
    """Retorna información estática de la Botillería El Buen Trago: horarios
    de atención, servicios ofrecidos y ubicación física.

    Invoca esta herramienta cuando el usuario pregunte por horarios de
    atención, ubicación, dirección, servicios disponibles, o cualquier
    dato general sobre la botillería (ej: 'a qué hora abren?', 'dónde
    están ubicados?', 'hacen delivery?', 'qué venden?'). NO la invoques
    para consultas sobre stock, precios de productos específicos, o temas
    que requieran datos dinámicos del inventario.

    Args:
        query: Texto opcional con la consulta del usuario sobre la
            botillería (ej: 'horario', 'ubicación', 'delivery'). Puede
            ser None si el contexto ya indica que se necesita información
            general sin una pregunta explícita.

    Returns:
        str: Cadena multilínea con el nombre de la botillería, horarios
            diferenciados por día (Lunes-Sábado vs Domingo), lista de
            servicios (licores, cervezas artesanales, vinos, pedidos a
            domicilio) y ubicación (Santiago, Chile).
    """
    return (
        "Botillería El Buen Trago.\n"
        "Horario: Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00.\n"
        "Servicios: Venta de licores, cervezas artesanales, vinos, pedidos a domicilio.\n"
        "Ubicación: Santiago, Chile."
    )


def consultar_stock(producto: str | None = None) -> str:
    """Inicia una consulta de disponibilidad de un producto específico en el
    inventario de la botillería.

    Invoca esta herramienta cuando el usuario pregunte si un producto está
    disponible, si tienen cierto licor/cerveza/vino en stock, o cuando
    exprese intención de comprar algo y necesites confirmar existencia
    (ej: 'tienen pisco sour?', 'hay cerveza artesanal de trigo?', 'tienen
    vino casillero del diablo?'). NO la invoques para preguntas sobre
    precios (usa consultar_precio), horarios (usa get_botilleria_info),
    o saludos generales. Si el usuario no especifica un producto, invoca
    la herramienta con producto=None para pedirle que especifique.

    Args:
        producto: Nombre del producto que el usuario busca, en formato
            texto libre (ej: 'pisco', 'vino tinto', 'cerveza artesanal',
            'whisky johnnie walker'). Usa None si el usuario no mencionó
            un producto específico y necesitas pedírselo.

    Returns:
        str: Mensaje de confirmación indicando que se consultará la
            disponibilidad del producto solicitado. Si producto fue
            proporcionado, incluye el nombre del producto en la respuesta.
            Si producto es None, retorna una pregunta solicitando al
            usuario que especifique qué producto le interesa.
    """
    if producto:
        return f"Stock de '{producto}': consultaré disponibilidad y te respondo pronto."
    return "¿Qué producto te interesa? Indícame el nombre y consultaré disponibilidad."


def consultar_precio(producto: str | None = None) -> str:
    """Inicia una consulta de precio para un producto específico de la
    botillería.

    Invoca esta herramienta cuando el usuario pregunte cuánto cuesta un
    producto, el valor de un licor/cerveza/vino, o solicite una cotización
    (ej: 'cuánto vale el pisco control?', 'precio del vino santa carolina',
    'cuánto cuesta la cerveza Kunstmann?'). NO la invoques para consultas
    de stock/disponibilidad (usa consultar_stock), horarios, o preguntas
    generales. Si el usuario no especifica un producto, invoca con
    producto=None para solicitar que lo indique.

    Args:
        producto: Nombre del producto cuyo precio se consulta, en formato
            texto libre (ej: 'pisco control 35°', 'vino reserva cabernet',
            'cerveza aura'). Usa None si el usuario no mencionó un
            producto específico y necesitas pedírselo.

    Returns:
        str: Mensaje de confirmación indicando que se consultará el precio
            del producto solicitado. Si producto fue proporcionado, incluye
            el nombre en la respuesta. Si producto es None, retorna una
            pregunta solicitando al usuario que especifique de qué producto
            quiere saber el precio.
    """
    if producto:
        return f"Precio de '{producto}': consultaré y te respondo pronto."
    return "¿De qué producto quieres saber el precio?"


def contactar_humano(motivo: str | None = None) -> str:
    """Solicita la transferencia de la conversación actual a un agente humano
    del equipo de la botillería.

    Invoca esta herramienta cuando el usuario solicite explícitamente hablar
    con una persona, cuando la consulta esté fuera del scope de tus
    capacidades (reclamos formales, consultas complejas de facturación,
    pedidos especiales que no puedes procesar), o cuando detectes que el
    usuario está frustrado o insatisfecho con la atención automatizada
    (ej: 'quiero hablar con alguien', 'necesito un humano', 'esto es un
    reclamo', 'me pueden contactar?'). NO la invoques para consultas
    rutinarias de stock, precios u horarios que puedes resolver con otras
    herramientas. Esta es tu última opción de escalación.

    Args:
        motivo: Razón o categoría de la transferencia, en formato texto
            libre (ej: 'consulta compleja', 'reclamo', 'pedido especial',
            'frustración del usuario'). Usa None si no hay un motivo
            explícito y la transferencia es por solicitud general del
            usuario.

    Returns:
        str: Confirmación de que la transferencia a un agente humano fue
            solicitada exitosamente. Incluye el motivo de la transferencia
            si fue proporcionado, o 'consulta general' como valor por
            defecto si motivo es None.
    """
    return f"Transferencia a humano solicitada. Motivo: {motivo or 'consulta general'}."


_BOTILLERIA_TOOLS = [
    get_current_datetime,
    get_botilleria_info,
    consultar_stock,
    consultar_precio,
    contactar_humano,
]


# ============================================================================
# AGENTE GADK — Patrón idéntico a booking-titanium-wm
# ============================================================================
# - LiteLlm + OpenRouter (NO Gemini directo)
# - Redis session backend en producción; memoria solo para fallback explícito
# - Agent/Runner cacheados (singleton por proceso)
# ============================================================================

_agent_cache: Agent | None = None
_runner_cache: Runner | None = None


def _get_agent() -> Agent:
    """Crea o retorna el agente ADK cacheado (singleton por proceso)."""
    global _agent_cache
    if _agent_cache is None:
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY no configurada. "
                "Configura la variable de entorno o agrega la clave a .env"
            )

        _agent_cache = Agent(
            name=f"{GADK_APP_NAME}_{int(time.time())}",
            model=LiteLlm(model=GADK_MODEL, api_key=openrouter_key),
            instruction=GADK_INSTRUCTION,
            tools=cast("list[Any]", _BOTILLERIA_TOOLS),
        )
    return _agent_cache


def _get_runner() -> Runner:
    """Crea o retorna el Runner ADK cacheado (singleton por proceso)."""
    global _runner_cache
    if _runner_cache is None:
        _runner_cache = Runner(
            agent=_get_agent(),
            app_name=GADK_APP_NAME,
            session_service=create_session_service(),
            auto_create_session=True,
        )
    return _runner_cache


def get_agent() -> Agent:
    """API pública: retorna el agente ADK."""
    return _get_agent()


def get_runner() -> Runner:
    """API pública: retorna el Runner ADK."""
    return _get_runner()
