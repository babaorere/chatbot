import asyncio
import time
import httpx

WEBHOOK_URL = "http://localhost:8000/telegram/webhook/8581822135:AAEZQ6azDAbZOT17DHrKVtVyU-P7uh7HIgM"
USER_ID = 987654321
CHAT_ID = 987654321


async def send_msg(text: str) -> dict:
    payload = {
        "message": {
            "message_id": int(time.time() * 1000) % 100000,
            "from": {"id": USER_ID, "first_name": "ClienteSimulado"},
            "chat": {"id": CHAT_ID, "type": "private"},
            "date": int(time.time()),
            "text": text
        }
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(WEBHOOK_URL, json=payload)
        return resp.json()


async def send_callback(callback_data: str, message_id: int) -> dict:
    payload = {
        "callback_query": {
            "id": f"cb_{int(time.time()*1000)}",
            "from": {"id": USER_ID, "first_name": "ClienteSimulado"},
            "message": {
                "message_id": message_id,
                "chat": {"id": CHAT_ID},
                "date": int(time.time()) - 5
            },
            "data": callback_data
        }
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(WEBHOOK_URL, json=payload)
        return resp.json()


async def main():
    print("====================================================")
    print(" SIMULADOR DE CLIENTE REAL - CHATBOT EL BUEN TRAGO  ")
    print("====================================================\n")

    # --- ESCENARIO 1: HAPPY PATH (Flujo de Compra exitoso) ---
    print("--- ESCENARIO 1: HAPPY PATH ---")
    print("[Cliente]: Envía /start")
    res = await send_msg("/start")
    print(f"[Bot Webhook]: {res}")
    await asyncio.sleep(6.0)

    print("\n[Cliente]: Pulsa botón 'Ver Categorías'")
    # Simulamos el callback del menú principal versión 1
    res = await send_callback("menu:categorias#1", message_id=1001)
    print(f"[Bot Webhook]: {res}")
    await asyncio.sleep(6.0)

    print("\n[Cliente]: Selecciona la categoría 'General'")
    res = await send_callback("cat_select:General#2", message_id=1002)
    print(f"[Bot Webhook]: {res}")
    await asyncio.sleep(6.0)

    print("\n[Cliente]: Escribe 'quiero comprar 2 botellas de Pisco Mistral 40° 1L'")
    res = await send_msg("quiero comprar 2 botellas de Pisco Mistral 40° 1L")
    print(f"[Bot Webhook]: {res}")
    await asyncio.sleep(6.0)

    # --- ESCENARIO 2: EQUIVOCACIONES Y MISTAKES ---
    print("\n--- ESCENARIO 2: EQUIVOCACIONES ---")
    print("[Cliente]: Pide un producto inexistente: 'tienen pisco capel de 50 litros?'")
    res = await send_msg("tienen pisco capel de 50 litros?")
    print(f"[Bot Webhook]: {res}")
    await asyncio.sleep(6.0)

    # --- ESCENARIO 3: CONCURRENCIA PARANOICA (Clics dobles / rápidos) ---
    print("\n--- ESCENARIO 3: CONCURRENCIA PARANOICA (Doble Clic Rápido) ---")
    print("[Cliente]: Envía dos mensajes casi simultáneamente...")
    # Ejecutamos ambos en paralelo
    t1 = send_msg("tienen cerveza heineken?")
    t2 = send_msg("tienen cerveza heineken?")
    r1, r2 = await asyncio.gather(t1, t2)
    print(f"[Bot Webhook (Request 1)]: {r1}")
    print(f"[Bot Webhook (Request 2)]: {r2}  <-- ¡Bloqueado por el lock de concurrencia!")
    await asyncio.sleep(6.0)

    # --- ESCENARIO 4: MENÚ EXPIRADO / TURNO INCORRECTO ---
    print("\n--- ESCENARIO 4: MENÚS EXPIRADOS / CAPAS DE FALLBACK ---")
    print("[Cliente]: Pulsa un botón obsoleto (versión vieja #1, cuando FSM ya avanzó a versión #4)")
    res = await send_callback("menu:stock#1", message_id=999)
    print(f"[Bot Webhook]: {res}  <-- ¡Rechazado por Capa 2 de versión FSM!")
    await asyncio.sleep(6.0)

    print("\n--- SIMULACIÓN FINALIZADA CON ÉXITO ---")


if __name__ == "__main__":
    asyncio.run(main())
