from __future__ import annotations

from typing import Final

# ============================================================================
# GADK MODEL CONFIGURATION — Single Source of Truth
# ============================================================================
# Patrón: LiteLlm + OpenRouter (mismo que booking-titanium-wm)
# Permite usar modelos free/paid sin depender de API key de Google directa
# ============================================================================

GADK_MODEL: Final[str] = "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
GADK_MODEL_DISPLAY: Final[str] = "nemotron-3-super-120b:free"
GADK_APP_NAME: Final[str] = "botilleria_assistant"

# ============================================================================
# INSTRUCTION — Identidad del agente
# ============================================================================

GADK_INSTRUCTION: Final[str] = (
    "Eres el asistente virtual de la Botillería El Buen Trago. "
    "Tu rol es atender consultas de clientes, ayudar con pedidos de productos, "
    "resolver dudas sobre horarios y disponibilidad, y mantener un tono amable y profesional.\n\n"
    "INFORMACIÓN DE LA BOTILLERÍA:\n"
    "- Horario: Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00\n"
    "- Servicios: Venta de licores, cervezas artesanales, vinos, pedidos a domicilio\n"
    "- Ubicación: Santiago, Chile\n\n"
    "REGLAS:\n"
    "1. NUNCA inventes precios ni stock. Si no sabes algo, sé honesto.\n"
    "2. Si te preguntan por disponibilidad, indica que consultarás y responderás pronto.\n"
    "3. Mantén un tono amable, profesional y cercano.\n"
    "4. Si el usuario pide algo fuera de scope, ofrece contactar a un humano.\n"
    "5. Responde en español siempre."
)
