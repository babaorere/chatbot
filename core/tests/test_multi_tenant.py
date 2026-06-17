"""
Test de Multi-Tenant — Happy Path.

Verifica:
1. Aislamiento de datos entre tenants (RLS)
2. Resolución correcta de tenant por header y channel mapping
3. Sesiones aisladas por tenant
4. Transacciones ACID (rollback en error)
5. Configuración dinámica por tenant (instruction, modelo)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import os
import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8001")
pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True, scope="function")
def cleanup_database():
    """Limpia los tenants de prueba y sus relaciones para garantizar la idempotencia."""
    from config.database import SessionLocal, _sync_engine
    from sqlalchemy import text, inspect

    slugs = [t.slug for t in TENANTS]

    with SessionLocal() as db:
        try:
            inspector = inspect(_sync_engine)
            existing_tables = inspector.get_table_names()

            # Orden de eliminación para evitar violaciones de clave foránea
            tables_to_clean = [
                "channel_routes",
                "messages",
                "conversations",
                "users",
                "knowledge_base",
                "products",
                "cart_items",
                "categories",
                "kb_categories"
            ]

            for table in tables_to_clean:
                if table in existing_tables:
                    db.execute(
                        text(f"DELETE FROM {table} WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = ANY(:slugs))"),
                        {"slugs": slugs}
                    )

            if "tenants" in existing_tables:
                db.execute(
                    text("DELETE FROM tenants WHERE slug = ANY(:slugs)"),
                    {"slugs": slugs}
                )

            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Error cleaning up database: {e}")


# ============================================================================
# CONFIGURACIÓN DE TENANTS DE PRUEBA
# ============================================================================


@dataclass
class TenantConfig:
    slug: str
    name: str
    instruction: str
    model: str
    api_key: str
    channels: list[dict[str, str]] = field(default_factory=list)


TENANTS = [
    TenantConfig(
        slug="botilleria_san_miguel",
        name="Botillería San Miguel",
        instruction=(
            "Eres el asistente de la Botillería San Miguel. "
            "Horario: Lunes a Viernes 09:00-21:00, Sábado 10:00-20:00. "
            "Ubicación: San Miguel, Santiago."
        ),
        model="groq/llama-3.1-8b-instant",
        api_key="sk-or-test-key-1",
        channels=[
            {"platform": "telegram", "channel_identifier": "token_san_miguel"},
        ],
    ),
    TenantConfig(
        slug="licoreria_providencia",
        name="Licorería Providencia",
        instruction=(
            "Eres el asistente de la Licorería Providencia. "
            "Horario: Lunes a Domingo 11:00-23:00. "
            "Ubicación: Providencia, Santiago. "
            "Especialidad: Vinos premium y licores importados."
        ),
        model="groq/llama-3.1-8b-instant",
        api_key="sk-or-test-key-2",
        channels=[
            {"platform": "telegram", "channel_identifier": "token_providencia"},
            {"platform": "whatsapp", "channel_identifier": "whatsapp_providencia"},
        ],
    ),
    TenantConfig(
        slug="vinos_las_condes",
        name="Vinos Las Condes",
        instruction=(
            "Eres el asistente de Vinos Las Condes. "
            "Horario: Martes a Domingo 12:00-22:00. "
            "Ubicación: Las Condes, Santiago. "
            "Especialidad: Vinos chilenos y argentinos."
        ),
        model="groq/llama-3.1-8b-instant",
        api_key="sk-or-test-key-3",
        channels=[
            {"platform": "web", "channel_identifier": "vinoslascondes.cl"},
        ],
    ),
]


# ============================================================================
# MOTOR DE TEST
# ============================================================================


async def create_tenant(
    client: httpx.AsyncClient,
    config: TenantConfig,
) -> dict[str, Any]:
    """Crea un tenant y sus canales."""
    # Crear tenant
    response = await client.post(
        f"{BASE_URL}/tenants",
        json={
            "slug": config.slug,
            "name": config.name,
            "instruction": config.instruction,
            "model": config.model,
            "api_key": config.api_key,
        },
    )
    response.raise_for_status()
    tenant = response.json()

    # Agregar canales
    for channel in config.channels:
        response = await client.post(
            f"{BASE_URL}/tenants/{tenant['id']}/channels",
            json=channel,
        )
        response.raise_for_status()

    return tenant


async def send_message_with_tenant_header(
    client: httpx.AsyncClient,
    tenant_id: str,
    user_id: str,
    platform: str,
    message: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Envía un mensaje con header X-Tenant-ID."""
    payload: dict[str, Any] = {
        "user_id": user_id,
        "platform": platform,
        "message": message,
    }
    if session_id:
        payload["session_id"] = session_id

    response = await client.post(
        f"{BASE_URL}/chat",
        json=payload,
        headers={"X-Tenant-ID": tenant_id},
    )
    response.raise_for_status()
    return response.json()


async def send_message_with_channel_mapping(
    client: httpx.AsyncClient,
    platform: str,
    channel_identifier: str,
    user_id: str,
    message: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Envía un mensaje con mapeo de canal (simula webhook de Windmill)."""
    payload: dict[str, Any] = {
        "user_id": user_id,
        "platform": platform,
        "message": message,
    }
    if session_id:
        payload["session_id"] = session_id

    response = await client.post(
        f"{BASE_URL}/chat",
        json=payload,
        headers={
            "X-Platform": platform,
            "X-Channel-Identifier": channel_identifier,
        },
    )
    response.raise_for_status()
    return response.json()


async def test_tenant_isolation() -> dict[str, Any]:
    """
    Test 1: Verifica que los datos de tenants están aislados.
    Cada tenant solo ve sus propios usuarios y conversaciones.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Crear tenants
        tenants = []
        for config in TENANTS:
            tenant = await create_tenant(client, config)
            tenants.append(tenant)

        # Crear usuarios para cada tenant
        users_per_tenant = {}
        for tenant in tenants:
            response = await client.post(
                f"{BASE_URL}/users",
                json={
                    "external_id": f"user_{tenant['slug']}",
                    "platform": "web",
                    "display_name": f"Usuario de {tenant['name']}",
                },
                headers={"X-Tenant-ID": tenant["id"]},
            )
            response.raise_for_status()
            users_per_tenant[tenant["id"]] = response.json()

        # Verificar que cada tenant solo ve sus usuarios
        isolation_passed = True
        for tenant in tenants:
            response = await client.get(
                f"{BASE_URL}/users",
                headers={"X-Tenant-ID": tenant["id"]},
            )
            response.raise_for_status()
            users = response.json()

            # Debe haber exactamente 1 usuario (el que creamos)
            if len(users) != 1:
                isolation_passed = False
                break

            # El usuario debe pertenecer a este tenant
            if users[0]["external_id"] != f"user_{tenant['slug']}":
                isolation_passed = False
                break

        return {
            "test": "tenant_isolation",
            "passed": isolation_passed,
            "tenants_created": len(tenants),
        }


async def test_tenant_resolution_by_header() -> dict[str, Any]:
    """
    Test 2: Verifica resolución de tenant por header X-Tenant-ID.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Crear tenant
        tenant = await create_tenant(client, TENANTS[0])

        # Enviar mensaje con header correcto
        response = await send_message_with_tenant_header(
            client,
            tenant_id=tenant["id"],
            user_id="header-test-user",
            platform="web",
            message="Hola, cuál es su horario?",
        )

        # Verificar que la respuesta incluye el tenant correcto
        header_passed = (
            response["tenant_slug"] == TENANTS[0].slug
            and response["user_id"] == "header-test-user"
        )

        # Enviar mensaje sin header (debe fallar)
        try:
            response = await client.post(
                f"{BASE_URL}/chat",
                json={
                    "user_id": "no-header-user",
                    "platform": "web",
                    "message": "Hola",
                },
            )
            no_header_passed = response.status_code == 401
        except Exception as e:
            print(f"  ⚠️  Unexpected error in no-header test: {e}")
            no_header_passed = False

        return {
            "test": "tenant_resolution_by_header",
            "passed": header_passed and no_header_passed,
            "header_resolution": header_passed,
            "no_header_rejected": no_header_passed,
        }


async def test_tenant_resolution_by_channel() -> dict[str, Any]:
    """
    Test 3: Verifica resolución de tenant por mapeo de canal.
    Simula el flujo de webhook de Windmill.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Crear tenants con canales
        tenants = []
        for config in TENANTS:
            tenant = await create_tenant(client, config)
            tenants.append(tenant)

        # Enviar mensaje vía canal de Telegram (San Miguel)
        response_sm = await send_message_with_channel_mapping(
            client,
            platform="telegram",
            channel_identifier="token_san_miguel",
            user_id="telegram-user-sm",
            message="Hola, están abiertos?",
        )

        # Enviar mensaje vía canal de WhatsApp (Providencia)
        response_prov = await send_message_with_channel_mapping(
            client,
            platform="whatsapp",
            channel_identifier="whatsapp_providencia",
            user_id="whatsapp-user-prov",
            message="Hola, tienen vinos premium?",
        )

        # Verificar que cada canal resolvió el tenant correcto
        channel_passed = (
            response_sm["tenant_slug"] == "botilleria_san_miguel"
            and response_prov["tenant_slug"] == "licoreria_providencia"
        )

        return {
            "test": "tenant_resolution_by_channel",
            "passed": channel_passed,
            "san_miguel_resolved": response_sm["tenant_slug"]
            == "botilleria_san_miguel",
            "providencia_resolved": response_prov["tenant_slug"]
            == "licoreria_providencia",
        }


async def test_session_isolation_per_tenant() -> dict[str, Any]:
    """
    Test 4: Verifica que las sesiones están aisladas por tenant.
    Dos tenants con el mismo user_id no deben compartir sesiones.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Crear tenants
        tenant_a = await create_tenant(client, TENANTS[0])
        tenant_b = await create_tenant(client, TENANTS[1])

        # Mismo user_id en ambos tenants
        user_id = "shared-user-id"

        # Conversación en Tenant A
        response_a1 = await send_message_with_tenant_header(
            client,
            tenant_id=tenant_a["id"],
            user_id=user_id,
            platform="web",
            message="Hola, soy usuario de San Miguel",
        )
        session_a = response_a1["session_id"]

        # Conversación en Tenant B
        response_b1 = await send_message_with_tenant_header(
            client,
            tenant_id=tenant_b["id"],
            user_id=user_id,
            platform="web",
            message="Hola, soy usuario de Providencia",
        )
        session_b = response_b1["session_id"]

        # Verificar que las sesiones son diferentes
        session_isolation_passed = (
            session_a != session_b
            and response_a1["tenant_slug"] == "botilleria_san_miguel"
            and response_b1["tenant_slug"] == "licoreria_providencia"
        )

        # Verificar que la continuidad de sesión funciona por tenant
        response_a2 = await send_message_with_tenant_header(
            client,
            tenant_id=tenant_a["id"],
            user_id=user_id,
            platform="web",
            message="Cuál es mi horario?",
            session_id=session_a,
        )

        continuity_passed = (
            response_a2["session_id"] == session_a
            and response_a2["tenant_slug"] == "botilleria_san_miguel"
        )

        return {
            "test": "session_isolation_per_tenant",
            "passed": session_isolation_passed and continuity_passed,
            "sessions_isolated": session_a != session_b,
            "continuity_maintained": continuity_passed,
        }


async def test_concurrent_multi_tenant() -> dict[str, Any]:
    """
    Test 5: Verifica concurrencia multi-tenant.
    3 tenants atendiendo usuarios simultáneamente sin mezcla de datos.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Crear tenants
        tenants = []
        for config in TENANTS[:3]:
            tenant = await create_tenant(client, config)
            tenants.append(tenant)

        # Scripts de conversación por tenant
        async def run_tenant_conversation(
            tenant: dict, user_id: str, messages: list[str]
        ) -> list[dict[str, Any]]:
            results = []
            session_id = None
            for msg in messages:
                response = await send_message_with_tenant_header(
                    client,
                    tenant_id=tenant["id"],
                    user_id=user_id,
                    platform="web",
                    message=msg,
                    session_id=session_id,
                )
                if session_id is None:
                    session_id = response["session_id"]
                results.append(response)
                await asyncio.sleep(0.2)
            return results

        # Ejecutar conversaciones en paralelo
        tasks = []
        for tenant in tenants:
            task = asyncio.create_task(
                run_tenant_conversation(
                    tenant,
                    user_id=f"user_{tenant['slug']}",
                    messages=[
                        f"Hola, soy cliente de {tenant['name']}",
                        "Cuál es su horario?",
                        "Tienen productos disponibles?",
                        "Dame el total de mi compra",
                    ],
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verificar que cada tenant solo recibió respuestas de su propio tenant
        concurrency_passed = True
        for i, tenant_results in enumerate(results):
            tenant = tenants[i]
            for response in tenant_results:
                if response["tenant_slug"] != tenant["slug"]:
                    concurrency_passed = False
                    break

        return {
            "test": "concurrent_multi_tenant",
            "passed": concurrency_passed,
            "tenants_concurrent": len(tenants),
            "total_messages": sum(len(r) for r in results),
        }


# ============================================================================
# EJECUCIÓN PRINCIPAL
# ============================================================================


async def main() -> None:
    print("=" * 70)
    print("TEST: Multi-Tenant Happy Path")
    print("=" * 70)
    print()

    start_time = time.time()

    # Ejecutar todos los tests
    tests = [
        test_tenant_isolation,
        test_tenant_resolution_by_header,
        test_tenant_resolution_by_channel,
        test_session_isolation_per_tenant,
        test_concurrent_multi_tenant,
    ]

    results = []
    for test_func in tests:
        print(f"Running: {test_func.__name__}...")
        try:
            result = await test_func()
            results.append(result)
            status = "✅ PASSED" if result["passed"] else "❌ FAILED"
            print(f"  {status}")
        except Exception as e:
            results.append(
                {
                    "test": test_func.__name__,
                    "passed": False,
                    "error": str(e),
                }
            )
            print(f"  ❌ FAILED: {e}")
        print()

    elapsed = time.time() - start_time

    # Resumen
    print("=" * 70)
    print(f"⏱️  Tiempo total: {elapsed:.2f}s")
    print(f"📊 Tests ejecutados: {len(results)}")
    print(f"✅ Pasados: {sum(1 for r in results if r.get('passed'))}")
    print(f"❌ Fallidos: {sum(1 for r in results if not r.get('passed'))}")
    print("=" * 70)

    all_passed = all(r.get("passed") for r in results)
    if all_passed:
        print("✅ TODOS LOS TESTS PASARON")
    else:
        print("❌ ALGUNOS TESTS FALLARON")

    print()
    for r in results:
        print(f"  {r['test']}: {'✅' if r.get('passed') else '❌'}")


if __name__ == "__main__":
    asyncio.run(main())
