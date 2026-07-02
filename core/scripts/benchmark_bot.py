import asyncio
import time
import httpx


async def benchmark_endpoint(name: str, payload: dict):
    url = "http://localhost:8000/telegram/webhook/8581822135:AAEZQ6azDAbZOT17DHrKVtVyU-P7uh7HIgM"
    start_time = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            elapsed = time.perf_counter() - start_time
            print(
                f"[{name}] HTTP Status: {resp.status_code} | Latencia: {elapsed:.3f} s"
            )
            return elapsed
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        print(f"[{name}] ERROR: {e} | Latencia: {elapsed:.3f} s")
        return elapsed


async def main():
    print("=== BENCHMARK DE LATENCIAS DEL BOT DE TELEGRAM ===")

    # 1. Comando /start (Respuestas estáticas, sin base de datos pesada ni LLM)
    start_payload = {
        "message": {
            "message_id": 100,
            "from": {"id": 5391760292},
            "chat": {"id": 5391760292},
            "date": int(time.time()),
            "text": "/start",
        }
    }
    await benchmark_endpoint("/start", start_payload)

    # Esperar un poco para no saturar
    await asyncio.sleep(0.5)

    # 2. Click en botón de Categorías (Consulta Base de Datos)
    cat_payload = {
        "callback_query": {
            "id": "cb_1",
            "from": {"id": 5391760292},
            "message": {
                "message_id": 101,
                "chat": {"id": 5391760292},
                "date": int(time.time()),
            },
            "data": "menu:categorias",
        }
    }
    await benchmark_endpoint("Callback: Categorías", cat_payload)

    await asyncio.sleep(0.5)

    # 3. Click en Categoría Específica (Consulta de productos filtrados)
    select_payload = {
        "callback_query": {
            "id": "cb_2",
            "from": {"id": 5391760292},
            "message": {
                "message_id": 102,
                "chat": {"id": 5391760292},
                "date": int(time.time()),
            },
            "data": "cat_select:General",
        }
    }
    await benchmark_endpoint("Callback: Seleccionar Categoría General", select_payload)

    await asyncio.sleep(0.5)

    # 4. Transición FSM (Ej: Consultar stock, cambia estado)
    stock_payload = {
        "callback_query": {
            "id": "cb_3",
            "from": {"id": 5391760292},
            "message": {
                "message_id": 103,
                "chat": {"id": 5391760292},
                "date": int(time.time()),
            },
            "data": "menu:stock",
        }
    }
    await benchmark_endpoint("Callback: Consultar Stock (FSM)", stock_payload)

    await asyncio.sleep(0.5)

    # 5. Texto libre "hola" (Inferencia con el LLM externo - DeepSeek)
    text_payload = {
        "message": {
            "message_id": 104,
            "from": {"id": 5391760292},
            "chat": {"id": 5391760292},
            "date": int(time.time()),
            "text": "hola",
        }
    }
    await benchmark_endpoint("Mensaje de Texto: 'hola' (LLM)", text_payload)


if __name__ == "__main__":
    asyncio.run(main())
