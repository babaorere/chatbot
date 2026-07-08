from __future__ import annotations

import datetime
import logging
import os
import time
from typing import Any, cast
from zoneinfo import ZoneInfo

from config.database import SessionLocal
from services.conversation_service import ConversationService
from services.product_service import ProductService
from services.session_service_factory import create_session_service
from config.settings import settings
from .context import current_session_id_var
from .constants import (
    GADK_APP_NAME,
    GADK_INSTRUCTION,
    GADK_MODEL,
    build_effective_instruction,
)

logger = logging.getLogger(__name__)
# ============================================================================
# TOOLS — Funciones que el agente puede llamar
# ============================================================================


def get_current_datetime(query: str | None = None) -> str:
    """Obtiene la fecha y hora actual de Chile en la zona horaria America/Santiago.

    Invoca esta herramienta cuando el usuario pregunte por la hora, la fecha,
    el día actual, o cuando necesites contexto temporal real para responder
    correctamente. NO la invoques en consultas sin dependencia temporal ni para
    inventar horarios del negocio; para eso usa la información del negocio.

    Args:
        query (str | None): Consulta opcional del usuario relacionada con tiempo
            o fecha en texto libre. Usa None cuando el contexto ya exige la hora
            actual aunque el usuario no la haya formulado literalmente.

    Returns:
        str: Texto en una sola línea con día de la semana, fecha, hora y la
            etiqueta de hora Chile, listo para incorporarse al contexto del modelo.
    """
    tz = ZoneInfo("America/Santiago")
    now = datetime.datetime.now(tz)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    return f"Fecha/hora actual: {dias[now.weekday()]} {now.strftime('%d/%m/%Y %H:%M')} (hora Chile)"


def get_chatbot_info(query: str | None = None) -> str:
    """Entrega información general y estática del negocio para responder consultas institucionales.

    Invoca esta herramienta cuando el usuario pregunte por horarios, ubicación,
    cobertura general, servicios disponibles o datos institucionales no
    dinámicos. NO la invoques para precios, stock, catálogo, compras o
    cotizaciones; esos casos deben resolverse con herramientas reales.

    Args:
        query (str | None): Consulta opcional del usuario sobre horarios,
            ubicación, servicios o información general del negocio. Usa None
            cuando el contexto ya requiere esa información.

    Returns:
        str: Texto multilínea con nombre del negocio, horario de atención,
            servicios generales y ubicación, listo para que el modelo lo use
            como respuesta o contexto.
    """
    return (
        "Negocio El Buen Trago.\n"
        "Horario: Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00.\n"
        "Servicios: Venta de licores, cervezas artesanales, vinos, pedidos a domicilio.\n"
        "Ubicación: Santiago, Chile."
    )


def consultar_stock(producto: str | None = None) -> str:
    """Consulta la disponibilidad real de un producto específico en el catálogo operativo.

    Invoca esta herramienta cuando el usuario pregunte si un producto existe,
    si está disponible o cuando necesites confirmar inventario antes de avanzar
    una intención de compra. NO la invoques para precios, horarios o preguntas
    generales; si no hay producto explícito, úsala con None para pedir precisión.

    Args:
        producto (str | None): Nombre del producto buscado en texto libre.
            Usa None cuando el usuario no haya especificado el producto exacto
            y sea necesario solicitarlo antes de consultar.

    Returns:
        str: Texto con una solicitud de precisión si falta el producto, o con
            una lista de coincidencias y su disponibilidad actual, o con un
            mensaje de falla controlada si la consulta no pudo completarse.
    """
    if not producto:
        return (
            "¿Qué producto te interesa? Indícame el nombre y consultaré disponibilidad."
        )

    db = SessionLocal()
    try:
        product_svc = ProductService(db)
        products = product_svc.search(producto, limit=3)
        if not products:
            return f"No encontré '{producto}' en nuestro catálogo de inventario actual. ¿Deseas consultar por otra opción?"

        lines = []
        for p in products:
            disp = "Disponible" if p.is_available and p.stock > 0 else "Agotado"
            lines.append(f"- {p.name}: {p.stock} {p.unit_of_measure or 'un'} ({disp})")
        return "Disponibilidad de stock encontrada:\n" + "\n".join(lines)
    except Exception:
        return f"Disculpas, no he podido consultar el inventario para '{producto}'. Intenta de nuevo más tarde."
    finally:
        db.close()


def consultar_precio(producto: str | None = None) -> str:
    """Consulta el precio vigente de un producto específico en el catálogo operativo.

    Invoca esta herramienta cuando el usuario pregunte cuánto cuesta un
    producto, pida una cotización simple o necesites responder con precios
    reales del catálogo. NO la invoques para validar stock, horarios o
    información general; si falta el producto, úsala con None para pedirlo.

    Args:
        producto (str | None): Nombre del producto cuyo precio se debe buscar
            en texto libre. Usa None cuando el usuario aún no haya indicado un
            producto concreto.

    Returns:
        str: Texto con una solicitud de precisión si falta el producto, o con
            una lista de coincidencias y sus precios vigentes, o con un mensaje
            de falla controlada si la consulta no pudo completarse.
    """
    if not producto:
        return "¿De qué producto quieres saber el precio?"

    db = SessionLocal()
    try:
        product_svc = ProductService(db)
        products = product_svc.search(producto, limit=3)
        if not products:
            return f"No encontré ningún precio para '{producto}' en nuestro catálogo. ¿Buscas algún otro producto?"

        lines = []
        for p in products:
            price_val = float(p.price) if p.price else 0.0
            price_str = f"${price_val:,.0f}" if price_val > 0 else "No especificado"
            lines.append(f"- {p.name}: {price_str} por {p.unit_of_measure or 'un'}")
        return "Precios vigentes:\n" + "\n".join(lines)
    except Exception:
        return f"Disculpas, no he podido consultar el catálogo de precios para '{producto}'."
    finally:
        db.close()


def contactar_humano(motivo: str | None = None) -> str:
    """Solicita la derivación de la conversación actual a un agente humano.

    Invoca esta herramienta cuando el usuario pida hablar con una persona, la
    consulta quede fuera de capacidad operativa del asistente, exista un
    reclamo, o detectes frustración persistente. NO la invoques para preguntas
    rutinarias que puedas resolver con stock, precios u otra información real.

    Args:
        motivo (str | None): Motivo libre de la derivación, como reclamo,
            consulta compleja, pedido especial o solicitud explícita de humano.
            Usa None cuando no exista un motivo textual claro.

    Returns:
        str: Confirmación textual de la derivación a humano, incluyendo el
            motivo recibido o el valor por defecto 'consulta general'.
    """
    session_id = current_session_id_var.get()
    if session_id:
        db = SessionLocal()
        try:
            conv_svc = ConversationService(db)
            conv = conv_svc.get_by_session_id(session_id)
            if conv:
                conv.is_bot_paused = True
                db.commit()
        except Exception as e:
            logger.exception(
                "Failed to pause conversation for human handoff [session_id=%s]",
                session_id,
            )
            raise RuntimeError(
                f"Failed to pause conversation for human handoff [session_id={session_id}]"
            ) from e
        finally:
            db.close()
    return f"Transferencia a humano solicitada. Motivo: {motivo or 'consulta general'}."


_CHATBOT_TOOLS = [
    get_current_datetime,
    get_chatbot_info,
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

_agent_cache: Any | None = None
_runner_cache: Any | None = None


def reset_agent_cache() -> None:
    """Limpia la caché del Agente y Runner para forzar su recreación en caliente."""
    global _agent_cache, _runner_cache
    _agent_cache = None
    _runner_cache = None
    logger.info("Agent and Runner cache cleared/reset")


def _get_agent() -> Any:
    """Crea o retorna el agente ADK cacheado (singleton por proceso).

    Evidencia del límite:
    - La importación de `google.adk` sigue disparando deprecations internas en
      2.3.0.
    - El agente solo se necesita cuando entra tráfico LLM, así que el coste de
      importación se difiere al primer uso del camino conversacional.
    """
    global _agent_cache
    if _agent_cache is None:
        from google.adk.models.lite_llm import LiteLlm
        from google.adk import Agent
        from repositories.system_setting_repository import SystemSettingRepository

        # Consultar la configuración del agente en la base de datos
        db = SessionLocal()
        try:
            repo = SystemSettingRepository(db)
            db_model_name = repo.get_value("model_name")
            db_fb1 = repo.get_value("fallback_model_1")
            db_fb2 = repo.get_value("fallback_model_2")
            db_api_key = repo.get_value("openrouter_api_key")
            db_instruction = repo.get_value("agent_instruction")
        except Exception as e:
            logger.warning(
                "Error reading agent settings from DB, using defaults: %s", e
            )
            db_model_name = None
            db_fb1 = None
            db_fb2 = None
            db_api_key = None
            db_instruction = None
        finally:
            db.close()

        model_name = db_model_name or settings.model_name or GADK_MODEL
        if "deepseek" in model_name.lower():
            api_key = (
                db_api_key
                or settings.deepseek_api_key
                or os.getenv("DEEPSEEK_API_KEY", "")
            )
            os.environ["DEEPSEEK_API_KEY"] = api_key
        else:
            api_key = (
                db_api_key
                or settings.openrouter_api_key
                or os.getenv("OPENROUTER_API_KEY", "")
            )

        fallbacks = []
        fb1_model = db_fb1 if db_fb1 is not None else settings.fallback_model_1
        if fb1_model and fb1_model.lower() not in ("none", "ninguno"):
            fb1_key = api_key
            if "groq" in fb1_model.lower():
                fb1_key = settings.groq_api_key or os.getenv("GROQ_API_KEY", "")
            elif "deepseek" in fb1_model.lower():
                fb1_key = settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")
            fallbacks.append({"model": fb1_model, "api_key": fb1_key})

        fb2_model = db_fb2 if db_fb2 is not None else settings.fallback_model_2
        if fb2_model and fb2_model.lower() not in ("none", "ninguno"):
            fb2_key = api_key
            if "groq" in fb2_model.lower():
                fb2_key = settings.groq_api_key or os.getenv("GROQ_API_KEY", "")
            elif "deepseek" in fb2_model.lower():
                fb2_key = settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")
            fallbacks.append({"model": fb2_model, "api_key": fb2_key})

        model_kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "num_retries": 3,
            "fallbacks": fallbacks,
        }
        if "deepseek" in model_name.lower():
            model_kwargs["thinking"] = {"type": settings.deepseek_thinking}

        model_obj = LiteLlm(**model_kwargs)
        instruction = build_effective_instruction(db_instruction or GADK_INSTRUCTION)

        _agent_cache = Agent(
            name=f"{GADK_APP_NAME}_{int(time.time())}",
            model=model_obj,
            instruction=instruction,
            tools=cast("list[Any]", _CHATBOT_TOOLS),
        )
    return _agent_cache


def _get_runner() -> Any:
    """Crea o retorna el Runner ADK cacheado (singleton por proceso).

    Esta importación queda encerrada aquí para mantener el arranque del proceso
    libre de ADK hasta que la ruta LLM realmente se ejecute.
    """
    global _runner_cache
    if _runner_cache is None:
        from google.adk import Runner

        _runner_cache = Runner(
            agent=_get_agent(),
            app_name=GADK_APP_NAME,
            session_service=create_session_service(),
            auto_create_session=True,
        )
    return _runner_cache


def get_agent() -> Any:
    """API pública: retorna el agente ADK."""
    return _get_agent()


def get_runner() -> Any:
    """API pública: retorna el Runner ADK."""
    return _get_runner()
