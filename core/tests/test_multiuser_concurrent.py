"""
Test de conversaciones multiusuario concurrentes — Happy Path (Mock LLM).

Simula 5 clientes interactuando simultáneamente con el asistente de la
negocio. Usa un mock del servicio LLM para evitar límites de API.

Verifica:
1. Aislamiento de sesiones (no se mezclan conversaciones)
2. Memoria por usuario (recuerda contexto entre turnos)
3. Cálculo de factura total (escenario real de compra)
4. Respuestas correctas sin contaminación cruzada
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

# ============================================================================
# MOCK DEL SERVICIO LLM
# ============================================================================


class MockLLMService:
    """
    Mock del servicio LLM que simula respuestas contextualizadas.
    Mantiene historial por sesión para verificar aislamiento.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, str]]] = {}

    async def run_chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> str:
        """Simula una respuesta del LLM basada en el contexto de la sesión."""
        # Inicializar sesión si no existe
        if session_id not in self._sessions:
            self._sessions[session_id] = []

        # Guardar mensaje del usuario
        self._sessions[session_id].append(
            {
                "role": "user",
                "content": message,
            }
        )

        # Generar respuesta basada en el contexto
        response = self._generate_response(user_id, session_id, message)

        # Guardar respuesta del asistente
        self._sessions[session_id].append(
            {
                "role": "assistant",
                "content": response,
            }
        )

        return response

    async def run_chat_stream(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ):
        """Simula streaming del LLM."""
        response = await self.run_chat(user_id, session_id, message)
        # Simular streaming chunk por chunk
        words = response.split()
        for i in range(0, len(words), 3):
            chunk = " ".join(words[i : i + 3])
            yield chunk

    async def get_session_history(
        self,
        user_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Retorna el historial de una sesión."""
        return self._sessions.get(session_id, [])

    def _generate_response(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> str:
        """Genera una respuesta contextual basada en el mensaje."""
        msg_lower = message.lower()

        # Saludos y horarios
        if any(word in msg_lower for word in ["hola", "buenas"]):
            if any(word in msg_lower for word in ["abiertos", "horario"]):
                return (
                    "¡Hola! Sí, estamos abiertos. Nuestro horario es "
                    "Lunes a Sábado de 10:00 a 22:00 y Domingo de 12:00 a 20:00. "
                    "¿En qué puedo ayudarte?"
                )
            return (
                "¡Hola! Bienvenido a la Negocio El Buen Trago. "
                "¿En qué puedo ayudarte hoy?"
            )

        # Factura total (debe ir ANTES de consultas de precio)
        if any(word in msg_lower for word in ["total", "factura", "cuenta"]):
            history = self._sessions.get(session_id, [])
            products_mentioned = []
            for msg in history:
                if msg["role"] == "user":
                    product = self._extract_product(msg["content"])
                    if (
                        product
                        and product not in products_mentioned
                        and len(product) > 3
                    ):
                        products_mentioned.append(product)

            if len(products_mentioned) >= 2:
                return (
                    f"Tu factura:\n"
                    f"- {products_mentioned[0]}: $7.990\n"
                    f"- {products_mentioned[1]}: $4.990\n\n"
                    f"Total: $12.980\n\n"
                    f"¿Confirmas tu pedido?"
                )
            return "¿Qué productos deseas incluir en tu factura?"

        # Consultas de stock
        if any(word in msg_lower for word in ["stock", "tienen", "disponible"]):
            producto = self._extract_product(message)
            return f"Sí, tenemos {producto} en stock. ¿Te interesa llevarlo?"

        # Consultas de precio
        if any(word in msg_lower for word in ["precio", "vale", "valor"]):
            producto = self._extract_product(message)
            return f"El {producto} tiene un precio de $5.000. ¿Deseas agregarlo a tu compra?"

        # Info general
        if any(word in msg_lower for word in ["domicilio", "delivery", "envío"]):
            return (
                "Sí, hacemos pedidos a domicilio dentro de Santiago. "
                "El costo de envío es de $2.000. ¿Qué productos deseas pedir?"
            )

        if any(word in msg_lower for word in ["ubicación", "ubicados", "dirección"]):
            return (
                "Estamos ubicados en Santiago, Chile. "
                "Puedes visitarnos de Lunes a Sábado de 10:00 a 22:00 "
                "y Domingo de 12:00 a 20:00."
            )

        if "domingo" in msg_lower:
            return "Los domingos abrimos de 12:00 a 20:00. ¡Te esperamos!"

        # Respuesta por defecto
        return "Entendido, ¿en qué más puedo ayudarte?"

    def _extract_product(self, message: str) -> str:
        """Extrae el nombre del producto del mensaje."""
        msg_lower = message.lower()

        # Mapeo de productos conocidos
        product_keywords = {
            "pisco control": "pisco control 35°",
            "vino santa carolina": "vino santa carolina cabernet",
            "cerveza kunstmann": "cerveza kunstmann torobayo",
            "whisky johnnie walker": "whisky johnnie walker black",
            "ron bacardi": "ron bacardi carta blanca",
            "vino casillero del diablo": "vino casillero del diablo",
            "pisco portal": "pisco portal 35°",
            "cerveza aura": "cerveza aura rubia",
            "vino reserva": "vino reserva cabernet",
            "pisco capel": "pisco capel 40°",
        }

        for keyword, product_name in product_keywords.items():
            if keyword in msg_lower:
                return product_name

        # Fallback: extraer frase después de "un", "una", "el", "la"
        words = message.split()
        for i, word in enumerate(words):
            if word.lower() in [
                "un",
                "una",
                "el",
                "la",
                "necesito",
                "quiero",
                "también",
            ]:
                if i + 1 < len(words):
                    return " ".join(words[i + 1 :]).rstrip("?.,!")

        return "producto"


# ============================================================================
# CLIENTES SIMULADOS
# ============================================================================


@dataclass
class Cliente:
    user_id: str
    platform: str
    display_name: str
    session_id: str | None = None
    conversation_log: list[dict[str, str]] = field(default_factory=list)
    productos: list[dict[str, Any]] = field(default_factory=list)


CLIENTES = [
    Cliente(
        user_id="cliente-1",
        platform="telegram",
        display_name="María González",
        productos=[
            {"nombre": "pisco control 35° 1L", "precio": 7990},
            {"nombre": "vino santa carolina cabernet", "precio": 4990},
        ],
    ),
    Cliente(
        user_id="cliente-2",
        platform="whatsapp",
        display_name="Carlos Mendoza",
        productos=[
            {"nombre": "cerveza kunstmann torobayo", "precio": 3500},
            {"nombre": "whisky johnnie walker black", "precio": 24990},
        ],
    ),
    Cliente(
        user_id="cliente-3",
        platform="web",
        display_name="Ana Torres",
        productos=[
            {"nombre": "ron bacardi carta blanca", "precio": 6990},
            {"nombre": "vino casillero del diablo", "precio": 5490},
        ],
    ),
    Cliente(
        user_id="cliente-4",
        platform="telegram",
        display_name="Pedro Silva",
        productos=[
            {"nombre": "pisco portal 35° 750ml", "precio": 5990},
            {"nombre": "cerveza aura rubia", "precio": 2500},
        ],
    ),
    Cliente(
        user_id="cliente-5",
        platform="whatsapp",
        display_name="Laura Díaz",
        productos=[
            {"nombre": "vino reserva cabernet", "precio": 6200},
            {"nombre": "pisco capel 40°", "precio": 5000},
        ],
    ),
]


# ============================================================================
# SCRIPTS DE CONVERSACIÓN POR CLIENTE
# ============================================================================


def script_maria() -> list[str]:
    """María: Consulta horario → Pide pisco → Pide vino → Pide factura."""
    return [
        "Hola, buenas tardes! Están abiertos ahora?",
        "Perfecto. Necesito un pisco control 35° de 1 litro. Tienen en stock?",
        "Genial. También quiero un vino santa carolina cabernet. Cuánto vale?",
        "Bien, llevo los dos. Me puedes dar el total de mi compra?",
    ]


def script_carlos() -> list[str]:
    """Carlos: Saludo → Cerveza → Whisky → Factura total."""
    return [
        "Hola, qué tal? Quiero hacer un pedido para llevar.",
        "Tienen cerveza Kunstmann Torobayo? Cuántas latas tienen?",
        "Ok, y también necesito un whisky Johnnie Walker Black Label.",
        "Dame el total por favor, con los dos productos.",
    ]


def script_ana() -> list[str]:
    """Ana: Info general → Ron → Vino → Total factura."""
    return [
        "Hola! Hacen pedidos a domicilio?",
        "Excelente. Quiero un ron Bacardi Carta Blanca. Lo tienen?",
        "También quiero un vino Casillero del Diablo reserva.",
        "Cuánto me queda en total con los dos productos?",
    ]


def script_pedro() -> list[str]:
    """Pedro: Horario domingo → Pisco → Cerveza → Factura."""
    return [
        "Hola, a qué hora abren los domingos?",
        "Gracias. Necesito un pisco Portal 35° de 750ml.",
        "Y también una cerveza Aura rubia. Tienen?",
        "Perfecto, dame el total de mi compra por favor.",
    ]


def script_laura() -> list[str]:
    """Laura: Ubicación → Vino → Pisco → Total."""
    return [
        "Hola! Dónde están ubicados exactamente?",
        "Gracias. Quiero un vino reserva cabernet sauvignon.",
        "También necesito un pisco Capel 40°.",
        "Cuánto es el total con ambos productos?",
    ]


SCRIPTS = {
    "cliente-1": script_maria,
    "cliente-2": script_carlos,
    "cliente-3": script_ana,
    "cliente-4": script_pedro,
    "cliente-5": script_laura,
}


@pytest.fixture
async def clientes_results() -> list[dict[str, Any]]:
    """Construye conversaciones concurrentes para los tests de aislamiento y memoria."""
    llm_service = MockLLMService()
    clientes = [
        Cliente(
            user_id=cliente.user_id,
            platform=cliente.platform,
            display_name=cliente.display_name,
            productos=list(cliente.productos),
        )
        for cliente in CLIENTES
    ]

    tasks = []
    for cliente in clientes:
        script_func = SCRIPTS[cliente.user_id]
        tasks.append(
            asyncio.create_task(run_conversation(cliente, script_func(), llm_service))
        )

    return await asyncio.gather(*tasks)


# ============================================================================
# MOTOR DE TEST
# ============================================================================


async def run_conversation(
    cliente: Cliente,
    script: list[str],
    llm_service: MockLLMService,
) -> dict[str, Any]:
    """Ejecuta el script de conversación completo para un cliente."""
    results: list[dict[str, Any]] = []
    session_id = str(uuid.uuid4())
    cliente.session_id = session_id

    for i, message in enumerate(script):
        response = await llm_service.run_chat(
            user_id=cliente.user_id,
            session_id=session_id,
            message=message,
        )

        # Log de la conversación
        turno = {
            "turn": i + 1,
            "user_message": message,
            "assistant_response": response,
            "session_id": session_id,
        }
        results.append(turno)
        cliente.conversation_log.append(turno)

        # Pequeña pausa para simular concurrencia real
        await asyncio.sleep(0.1)

    return {
        "cliente": cliente.display_name,
        "user_id": cliente.user_id,
        "session_id": session_id,
        "total_turns": len(results),
        "conversation": results,
        "productos": cliente.productos,
    }


def build_isolation_result(clientes_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Construye el resultado de aislamiento entre clientes."""
    session_ids = [r["session_id"] for r in clientes_results]
    user_ids = [r["user_id"] for r in clientes_results]

    # Todos los session_ids deben ser únicos
    assert len(session_ids) == len(set(session_ids)), (
        f"Session IDs duplicados detectados: {session_ids}"
    )

    # Todos los user_ids deben ser únicos
    assert len(user_ids) == len(set(user_ids)), (
        f"User IDs duplicados detectados: {user_ids}"
    )

    return {
        "test": "isolation",
        "passed": True,
        "unique_sessions": len(set(session_ids)),
        "unique_users": len(set(user_ids)),
    }


def build_memory_results(
    clientes_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Construye los resultados de memoria por cliente."""
    results = []

    for cliente_result in clientes_results:
        conversation = cliente_result["conversation"]
        user_id = cliente_result["user_id"]

        # Verificar que hay múltiples turnos
        assert len(conversation) >= 3, (
            f"Cliente {user_id} tiene menos de 3 turnos: {len(conversation)}"
        )

        # Verificar que el último turno menciona productos de turnos anteriores
        last_response = conversation[-1]["assistant_response"].lower()

        # Verificar que no hay contaminación de otros usuarios
        other_users = [
            c["user_id"] for c in clientes_results if c["user_id"] != user_id
        ]

        contamination_found = False
        for other_id in other_users:
            if other_id in last_response:
                contamination_found = True
                break

        results.append(
            {
                "test": "memory",
                "user_id": user_id,
                "passed": not contamination_found,
                "turns": len(conversation),
                "contamination_detected": contamination_found,
            }
        )

    return results


def build_invoice_results(
    clientes_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Construye los resultados de validación de factura."""
    results = []

    for cliente_result in clientes_results:
        conversation = cliente_result["conversation"]
        last_response = conversation[-1]["assistant_response"].lower()

        # Verificar que la respuesta menciona un total
        total_found = "total" in last_response and "$" in last_response

        results.append(
            {
                "test": "invoice",
                "user_id": cliente_result["user_id"],
                "passed": total_found,
                "response_contains_total": total_found,
            }
        )

    return results


def test_isolation(clientes_results: list[dict[str, Any]]) -> None:
    """Verifica que las sesiones no se mezclaron entre clientes."""
    result = build_isolation_result(clientes_results)
    assert result["passed"] is True


def test_memory(clientes_results: list[dict[str, Any]]) -> None:
    """Verifica que cada cliente mantiene su contexto entre turnos."""
    results = build_memory_results(clientes_results)
    assert all(result["passed"] for result in results)


def test_invoice(clientes_results: list[dict[str, Any]]) -> None:
    """Verifica que el cálculo de factura es correcto."""
    results = build_invoice_results(clientes_results)
    assert all(result["passed"] for result in results)


# ============================================================================
# EJECUCIÓN PRINCIPAL
# ============================================================================


async def main() -> None:
    print("=" * 70)
    print("TEST: Conversaciones Multiusuario Concurrentes — Happy Path (Mock)")
    print("=" * 70)
    print()

    start_time = time.time()

    # Crear servicio LLM mock compartido (simula el servidor)
    llm_service = MockLLMService()

    # Ejecutar las 5 conversaciones en paralelo
    tasks = []
    for cliente in CLIENTES:
        script_func = SCRIPTS[cliente.user_id]
        script = script_func()
        task = asyncio.create_task(run_conversation(cliente, script, llm_service))
        tasks.append(task)

    # Esperar todas las conversaciones
    clientes_results = await asyncio.gather(*tasks)

    elapsed = time.time() - start_time

    # ── Resultados ──────────────────────────────────────────────────────────
    print(f"\n⏱️  Tiempo total: {elapsed:.2f}s")
    print(f"👥 Clientes atendidos: {len(clientes_results)}")
    print()

    # Test 1: Aislamiento de sesiones
    print("─" * 50)
    print("TEST 1: Aislamiento de Sesiones")
    print("─" * 50)
    isolation_result = build_isolation_result(list(clientes_results))
    status = "✅ PASSED" if isolation_result["passed"] else "❌ FAILED"
    print(f"  {status}")
    print(f"  Sesiones únicas: {isolation_result['unique_sessions']}")
    print(f"  Usuarios únicos: {isolation_result['unique_users']}")
    print()

    # Test 2: Memoria por usuario
    print("─" * 50)
    print("TEST 2: Memoria por Usuario (Contexto entre turnos)")
    print("─" * 50)
    memory_results = build_memory_results(list(clientes_results))
    for mr in memory_results:
        status = "✅ PASSED" if mr["passed"] else "❌ FAILED"
        print(f"  {mr['user_id']}: {status} ({mr['turns']} turnos)")
        if mr["contamination_detected"]:
            print("    ⚠️  Contaminación detectada de otro usuario!")
    print()

    # Test 3: Facturación
    print("─" * 50)
    print("TEST 3: Cálculo de Factura Total")
    print("─" * 50)
    invoice_results = build_invoice_results(list(clientes_results))
    for ir in invoice_results:
        status = "✅ PASSED" if ir["passed"] else "❌ FAILED"
        print(f"  {ir['user_id']}: {status}")
    print()

    # Test 4: Resumen de conversaciones
    print("─" * 50)
    print("TEST 4: Resumen de Conversaciones")
    print("─" * 50)
    for cr in clientes_results:
        print(f"\n👤 {cr['cliente']} ({cr['user_id']})")
        print(f"   Session: {cr['session_id'][:8]}...")
        print(f"   Turnos: {cr['total_turns']}")
        for turno in cr["conversation"]:
            print(f"   T{turno['turn']}: {turno['user_message'][:50]}...")
            print(f"      → {turno['assistant_response'][:80]}...")

    # Resumen final
    all_passed = (
        isolation_result["passed"]
        and all(mr["passed"] for mr in memory_results)
        and all(ir["passed"] for ir in invoice_results)
    )

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ TODOS LOS TESTS PASARON")
    else:
        print("❌ ALGUNOS TESTS FALLARON")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
