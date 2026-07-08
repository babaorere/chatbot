# Plan de reevaluacion con red team

## Objetivo

Reevaluar y continuar el plan de optimizacion de latencia del bot Telegram con evidencia del runtime Docker real, buscando fallas de arquitectura, medicion, cache, concurrencia y operacion antes de seguir agregando optimizaciones.

Este documento es el plan operativo vigente. Si una prueba contradice una premisa anterior, primero se actualiza este plan y luego se modifica codigo.

## Evidencia runtime aprendida

- Docker local real levantado con `api`, `db`, `redis` y `arq_worker`.
- `api`, `db`, `redis` y `arq_worker` quedaron `healthy`.
- `/health` reporta `arq.worker_status=ok`.
- Redis local contiene heartbeat ARQ en `chatbot:jobs:health`.
- La DB contiene 10 productos disponibles.
- Todos los productos sembrados quedaron en categoria `General`.
- El cache de catalogo queda con `1 categories, 10 products cached`.
- Se corrigio el orden de arranque: primero seed demo, luego `catalog_cache_primed`.
- Webhook sintetico `/start` respondio `200 scheduled`.
- Medicion real: `webhook_response_ready=1.42ms`.
- Medicion real: `background_started_after_webhook=2.68ms`.
- Medicion real: `sendMessage=1185.24ms` con chat falso y error Telegram 400, fuera del path critico.
- RT-5 ejecutado el 2026-07-08: 5 reinicios consecutivos de `api`, todos `healthy`.
- RT-5 confirmo 10 productos exactos y `General:10` despues de cada reinicio.
- RT-5 confirmo en logs el orden `Sembrado de productos generales finalizado` antes de `catalog_cache_primed`.

## Hallazgos corregidos durante la validacion

- `REDIS_URL` de `.env` apuntaba a Redis externo y dejaba el Redis local sin uso efectivo por API/ARQ.
- `docker-compose.yml` ahora fuerza `REDIS_URL=redis://redis:6379/0` para `api` y `arq_worker` en el stack local.
- `editMessageReplyMarkup` enviaba `reply_markup=null`; Telegram respondia `400 object expected`.
- La limpieza de reply markup ahora envia `{"inline_keyboard": []}`.
- `prime_human_agent_cache()` tenia un efecto colateral: tambien primeaba catalogo.
- El prime de catalogo ahora se ejecuta explicitamente en `lifespan` despues del seed demo.

## Regla de red team

Cada bloque debe intentar invalidar una premisa del plan, no confirmarla. Si el resultado es ambiguo, se considera riesgo abierto hasta tener medicion reproducible.

El red team corre en paralelo cuando las pruebas no compiten por el mismo estado. Pruebas que mutan DB, Redis, FSM o colas deben usar usuarios, keys o bases aisladas.

## Frentes paralelos

### RT-1. Latencia real de Telegram

Objetivo: probar que el webhook siempre libera al cliente antes de trabajos lentos.

Pruebas:
- Enviar 20 webhooks `/start` sinteticos con usuarios distintos.
- Medir `webhook_response_ready`, `background_started_after_webhook`, `webhook_to_background_finished`.
- Separar latencia de API local, Redis lock, DB, FSM, Telegram API externa y LLM.
- Confirmar que errores de `sendMessage` no cambian el tiempo de respuesta del webhook.

Criterio de fallo:
- `webhook_response_ready` p95 mayor a 50ms en runtime local sin carga externa pesada.
- Cualquier llamada a Telegram, LLM o DB larga antes de `webhook_response_ready`.

### RT-2. Cache vs verdad transaccional

Objetivo: demostrar que la cache acelera navegacion sin convertirse en verdad operacional.

Pruebas:
- Mutar catalogo por flujo admin o script controlado.
- Confirmar que la mutacion actualiza Postgres.
- Confirmar bump de version distribuida en Redis.
- Confirmar que otro proceso refresca cache cuando ve version remota mayor.
- Confirmar que carrito, checkout, pedidos y stock final siguen consultando DB.

Criterio de fallo:
- Navegacion usa productos obsoletos despues de mutacion confirmada.
- Checkout, stock o pedidos dependen de cache de catalogo.
- Cache se refresca antes de commit.

### RT-3. Redis/ARQ real

Objetivo: asegurar que los jobs durables existen, son observables y no bloquean respuestas.

Pruebas:
- Encolar `job_healthcheck` y verificar ejecucion por ARQ.
- Encolar cleanup de reply markup con payload serializable.
- Forzar Redis caido y verificar que fallos de jobs no bloquean `answerCallbackQuery`.
- Verificar heartbeat fresco cada 15s y `/health` `worker_status=ok`.

Criterio de fallo:
- Worker healthy por proceso vivo pero sin heartbeat.
- Job payload contiene objetos no serializables o dependencias runtime.
- Falla ARQ bloquea respuesta inmediata del usuario.

### RT-4. Concurrencia por usuario

Objetivo: romper supuestos de orden y locks.

Pruebas:
- Enviar updates concurrentes del mismo usuario.
- Enviar updates concurrentes de usuarios distintos.
- Medir espera por lock Redis.
- Verificar que un usuario no bloquea al resto.
- Saturar cleanup cosmetico y confirmar drop controlado sin romper flujo.

Criterio de fallo:
- Locks globales bloquean usuarios no relacionados.
- Dos updates del mismo usuario corrompen FSM.
- Cleanup cosmetico retrasa callback ack.

### RT-5. Arranque, seed y cache

Objetivo: validar que cada reinicio Docker deja DB y cache consistentes.

Estado: completado.

Evidencia:
- Ciclo 1: `api_health=healthy`, `product_total=10`, `category_counts=["General:10"]`.
- Ciclo 2: `api_health=healthy`, `product_total=10`, `category_counts=["General:10"]`.
- Ciclo 3: `api_health=healthy`, `product_total=10`, `category_counts=["General:10"]`.
- Ciclo 4: `api_health=healthy`, `product_total=10`, `category_counts=["General:10"]`.
- Ciclo 5: `api_health=healthy`, `product_total=10`, `category_counts=["General:10"]`.
- Logs de los 5 ciclos muestran `Sembrado de productos generales finalizado` antes de `catalog_cache_primed`.

Pruebas:
- [x] Reiniciar `api` 5 veces.
- [x] Confirmar 10 productos exactos y categoria `General`.
- [x] Confirmar que `catalog_cache_primed` aparece despues de `Sembrado de productos generales finalizado`.
- [x] Confirmar que Redis local, no Redis externo, es el backend del stack.

Criterio de fallo:
- Duplicados de productos.
- Cache primeado antes del seed.
- Healthcheck ARQ apunta a Redis distinto al worker.

### RT-6. Observabilidad

Objetivo: asegurar que los logs permiten diagnosticar latencia sin leer codigo.

Pruebas:
- Pasar logs reales por `core/scripts/analyze_telegram_latency.py`.
- Confirmar agrupacion por trace.
- Confirmar slowest stage.
- Confirmar cache version y age.
- Confirmar visibilidad de `sendMessage` y `answerCallbackQuery`.

Criterio de fallo:
- Un trace no permite reconstruir llamada, ack, background y salida externa.
- El analizador mezcla traces o pierde stages criticos.

## Orden recomendado

1. Ejecutar RT-5 para cerrar consistencia de arranque.
2. Ejecutar RT-3 para cerrar Redis/ARQ real.
3. Ejecutar RT-1 con usuarios sinteticos.
4. Ejecutar RT-4 con concurrencia controlada.
5. Ejecutar RT-2 con mutaciones reales de catalogo.
6. Ejecutar RT-6 con logs de todos los escenarios anteriores.

## Cambios esperados del plan vigente

- Mantener Postgres como verdad transaccional.
- Mantener cache solo para lectura estable y navegacion.
- Elevar la validacion Docker/ARQ a gate obligatorio antes de cerrar fases de background jobs.
- Agregar prueba de orden `seed -> prime_catalog_cache` como contrato permanente.
- Agregar prueba de Redis interno en compose local para evitar que `.env` apunte el stack a Redis externo accidentalmente.

## Salida esperada

Al terminar esta reevaluacion debe existir:

- Reporte de latencia p50/p95/p99 por stage.
- Tabla de fallos red-team con estado: corregido, reproducible pendiente, o descartado con evidencia.
- Actualizacion de este plan si algun paso queda reemplazado.
- Tests automatizados para todo hallazgo corregido.
- Validacion Docker final con `api`, `db`, `redis` y `arq_worker` healthy.
