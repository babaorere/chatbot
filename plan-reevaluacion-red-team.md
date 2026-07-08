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
- El hook local ejecutaba `pytest` dentro del contenedor `chatbot_api` contra la DB runtime `chatbot`; los tests truncaban `products`.
- `core/tests/conftest.py` ahora deriva automaticamente una DB aislada `chatbot_test` fuera de GitHub Actions cuando no se define `TEST_DATABASE_URL`, evitando destruir datos runtime durante validaciones locales.
- `core/scripts/analyze_telegram_latency.py` ahora acepta `--aggregate` para reportar p50/p95/p99/max por stage sin perder el detalle por trace.
- El worker ARQ ahora configura logging propio y `job_clear_reply_markup` registra inicio/fallo/exito con `event_id`, `trace_id`, `user_id`, `message_id` y retry.

## Regla de red team

Cada bloque debe intentar invalidar una premisa del plan, no confirmarla. Si el resultado es ambiguo, se considera riesgo abierto hasta tener medicion reproducible.

El red team corre en paralelo cuando las pruebas no compiten por el mismo estado. Pruebas que mutan DB, Redis, FSM o colas deben usar usuarios, keys o bases aisladas.

## Frentes paralelos

### RT-1. Latencia real de Telegram

Objetivo: probar que el webhook siempre libera al cliente antes de trabajos lentos.

Estado: completado.

Evidencia:
- 20 webhooks sinteticos `/start` enviados con usuarios distintos.
- Todos respondieron HTTP 200.
- Tiempo externo `curl`: minimo aproximado `2.36ms`, maximo aproximado `5.26ms`.
- `webhook_response_ready`: count=20, p50=`0.74ms`, p95=`1.28ms`, p99=`1.44ms`, max=`1.48ms`.
- `background_started_after_webhook`: count=20, p50=`1.18ms`, p95=`1.89ms`, p99=`1.91ms`, max=`1.92ms`.
- `sendMessage`: count=20, p50=`1475.64ms`, p95=`1635.21ms`, p99=`2728.90ms`, max=`3002.32ms`.
- `webhook_to_background_finished`: count=20, p50=`1486.43ms`, p95=`1638.90ms`, p99=`2733.11ms`, max=`3006.66ms`.
- No faltaron traces con `webhook_response_ready`.
- El tramo lento fue `sendMessage` externo en background; no bloqueo la respuesta inmediata del webhook.

Pruebas:
- [x] Enviar 20 webhooks `/start` sinteticos con usuarios distintos.
- [x] Medir `webhook_response_ready`, `background_started_after_webhook`, `webhook_to_background_finished`.
- [x] Separar latencia de API local, Redis lock, DB, FSM, Telegram API externa y LLM.
- [x] Confirmar que errores de `sendMessage` no cambian el tiempo de respuesta del webhook.

Criterio de fallo:
- `webhook_response_ready` p95 mayor a 50ms en runtime local sin carga externa pesada.
- Cualquier llamada a Telegram, LLM o DB larga antes de `webhook_response_ready`.

### RT-2. Cache vs verdad transaccional

Objetivo: demostrar que la cache acelera navegacion sin convertirse en verdad operacional.

Estado: completado.

Evidencia:
- Se detecto una precondicion rota antes de RT-2: `products=0` en `chatbot` porque el pre-commit habia ejecutado tests destructivos contra la DB runtime.
- Se corrigio el aislamiento de tests: suite local usa `chatbot_test`; despues de `pytest`, `chatbot` mantuvo `10` productos y `0` productos RT-2 temporales.
- Mutacion real por endpoint admin `POST /business/config/products` creo `RT2 Cache Probe HTTP 1783537118`.
- Postgres confirmo la mutacion: `products=11`, `rt2=1`.
- Redis publico version distribuida `1` en `chatbot:adk:v1:catalog:snapshot_version`.
- Logs API confirmaron `Catalog cache primed successfully: 1 categories, 11 products cached, version=2`.
- Logs API confirmaron `distributed_version_bumped ... version=1 reason=business_config_product_created`.
- Proceso Python separado inicializo Redis, partio con `seen=0` y ejecuto `_refresh_catalog_cache_if_remote_version_changed`.
- El proceso separado confirmo refresh por version remota: `seen=1`, `products=11`, `rt2=1`.
- Borrado real por endpoint admin `DELETE /business/config/products/{id}` elimino el producto temporal.
- Postgres confirmo limpieza: `products=10`, `rt2=0`.
- Redis publico version distribuida `2`.
- Logs API confirmaron `Catalog cache primed successfully: 1 categories, 10 products cached, version=3`.
- Proceso separado confirmo refresh post-delete: `seen=2`, `products=10`, `rt2=0`.
- Test automatizado agregado: `test_checkout_uses_db_stock_when_catalog_cache_is_stale`.
- El test fuerza `_catalog_snapshot` con stock obsoleto `99`, pero DB tiene stock real `1` y carrito pide `2`; checkout falla por `Stock insuficiente` y no descuenta stock.

Pruebas:
- [x] Mutar catalogo por flujo admin o script controlado.
- [x] Confirmar que la mutacion actualiza Postgres.
- [x] Confirmar bump de version distribuida en Redis.
- [x] Confirmar que otro proceso refresca cache cuando ve version remota mayor.
- [x] Confirmar que carrito, checkout, pedidos y stock final siguen consultando DB.

Criterio de fallo:
- Navegacion usa productos obsoletos despues de mutacion confirmada.
- Checkout, stock o pedidos dependen de cache de catalogo.
- Cache se refresca antes de commit.

### RT-3. Redis/ARQ real

Objetivo: asegurar que los jobs durables existen, son observables y no bloquean respuestas.

Estado: parcialmente completado.

Evidencia:
- `api` y `arq_worker` usan `REDIS_URL=redis://redis:6379/0`.
- Redis local contiene heartbeat fresco en `chatbot:jobs:health`.
- `/health` reporta `arq.worker_status=ok`.
- Job real `job_healthcheck` encolado con id `redteam:job-healthcheck:1783532993`.
- ARQ ejecuto el job y devolvio `status=ok`, `worker=arq`, `queue_name=chatbot:jobs`.
- Webhook sintetico durante ARQ/Redis activo respondio `200 scheduled`.
- Medicion interna: `webhook_response_ready=2.98ms`.
- Medicion interna: `background_started_after_webhook=3.59ms`.
- Medicion interna: `sendMessage=1249.45ms` fallo en background por chat sintetico, sin bloquear webhook.
- Job real `job_clear_reply_markup` encolado con id `redteam:clear-reply-markup:rt3-clear-reply-markup-1783538453`.
- ARQ ejecuto `job_clear_reply_markup`; Telegram externo fallo por token/chat sintetico, sin dejar retry pendiente.
- Se detecto que el log propio del worker no salia en `docker compose logs`; se corrigio configurando logging en `workers/arq_worker.py`.
- Segundo job real `job_clear_reply_markup` encolado con id `redteam:clear-reply-markup:rt3-clear-reply-markup-logs-1783538584`.
- Logs runtime confirmaron payload observable: `event_id=rt3-clear-reply-markup-logs-1783538584`, `trace_id=rt3:clear-reply-markup:logs`, `user_id=730003002`, `message_id=930003002`, `retry=1`.
- Logs runtime confirmaron llamada externa: `editMessageReplyMarkup elapsed_ms=1216.75 status=404 ok=False`.
- Resultados ARQ sinteticos de RT-3 fueron limpiados de Redis despues de capturar evidencia.
- `/health` posterior siguio reportando `arq.worker_status=ok`.

Pruebas:
- [x] Encolar `job_healthcheck` y verificar ejecucion por ARQ.
- [x] Encolar cleanup de reply markup con payload serializable en runtime real.
- [ ] Forzar Redis caido y verificar que fallos de jobs no bloquean `answerCallbackQuery`.
- [x] Verificar heartbeat fresco cada 15s y `/health` `worker_status=ok`.

Pendiente destructivo:
- Apagar Redis en este stack activo puede afectar sesiones reales y el tunnel local. Ejecutar solo en ventana controlada o con compose aislado.

Criterio de fallo:
- Worker healthy por proceso vivo pero sin heartbeat.
- Job payload contiene objetos no serializables o dependencias runtime.
- Falla ARQ bloquea respuesta inmediata del usuario.

### RT-4. Concurrencia por usuario

Objetivo: romper supuestos de orden y locks.

Estado: completado.

Evidencia:
- Prueba `same-user`: 10 updates concurrentes del usuario sintetico `720004001`.
- Resultado HTTP `same-user`: 10 respuestas `200`; 1 `scheduled`; 9 `duplicate request blocked`.
- Redis lock `same-user`: 1 `acquired=True`; 9 `acquired=False`.
- `same-user` `webhook_response_ready`: count=10, p50=`8.69ms`, p95=`9.01ms`, max=`9.36ms`.
- El unico background permitido en `same-user` continuo fuera del path critico; `process_message_uc_done=9410.07ms`, `sendMessage=794.03ms`, `webhook_to_background_finished=10220.91ms`.
- Prueba `different-users`: 10 updates concurrentes de usuarios sinteticos `720004100` a `720004109`.
- Resultado HTTP `different-users`: 10 respuestas `200`; 10 `scheduled`.
- Redis lock `different-users`: 10 `acquired=True`.
- `different-users` `webhook_response_ready`: count=10, p50=`6.73ms`, p95=`9.95ms`, max=`10.53ms`.
- `different-users` `background_started_after_webhook`: count=10, p50=`9.00ms`, p95=`11.36ms`, max=`11.41ms`.
- Prueba callback/cleanup: 12 callbacks concurrentes de usuarios sinteticos `720004200` a `720004211`.
- Resultado HTTP callback/cleanup: 12 respuestas `200`; 12 `scheduled`.
- Callback `webhook_response_ready`: count=12, p50=`9.28ms`, p95=`13.84ms`, max=`14.32ms`.
- `answerCallbackQuery` fue lento y fallo por IDs sinteticos falsos, pero ocurrio fuera del path critico: count=12, p50=`1854.91ms`, p95=`2049.00ms`, max=`2639.07ms`.
- `sendMessage` tambien fallo por chats sinteticos falsos, fuera del path critico: count=12, p50=`2384.31ms`, p95=`2936.94ms`, max=`3320.00ms`.
- Saturacion de cleanup cosmetico reproducida: 8 `reply_markup_clear_dropped` controlados en `0.02ms` a `0.07ms`.
- Cleanup ARQ en runtime real: 2 `reply_markup_clear_enqueued`, p50=`247.61ms`.
- `core/scripts/analyze_telegram_latency.py` reconstruyo traces de callback con `webhook_ack`, `background_total`, `callback_validated`, `sendMessage`, `answerCallbackQuery` y cache.

Pruebas:
- [x] Enviar updates concurrentes del mismo usuario.
- [x] Enviar updates concurrentes de usuarios distintos.
- [x] Medir espera por lock Redis.
- [x] Verificar que un usuario no bloquea al resto.
- [x] Saturar cleanup cosmetico y confirmar drop controlado sin romper flujo.

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

Estado: completado.

Evidencia:
- `core/scripts/analyze_telegram_latency.py --aggregate` se ejecuto sobre logs reales del contenedor `api`.
- El analizador produjo `56` lineas por trace y `28` lineas agregadas por stage.
- Los traces reconstruyen `webhook_ack`, `background_total`, `callback_validated`, `menu_stack_snapshot`, `sendMessage`, `answerCallbackQuery`, slowest stage y cache.
- Ejemplo de trace reconstruido: `trace=tg:720004211:920004211 webhook_ack=12.84ms background_total=1985.55ms callback_validated=14.51ms menu_stack_snapshot=0.00ms sendMessage=1945.24ms answerCallbackQuery=1364.96ms slowest=timing:webhook_to_background_finished:1985.55ms cache=v1 age=1912.69s`.
- `webhook_response_ready`: count=53, p50=`4.47ms`, p95=`13.59ms`, p99=`14.32ms`, max=`14.32ms`.
- `sendMessage`: count=44, p50=`1557.23ms`, p95=`2936.94ms`, p99=`3320.00ms`, max=`3320.00ms`.
- `answerCallbackQuery`: count=12, p50=`1850.22ms`, p95=`2639.07ms`, p99=`2639.07ms`, max=`2639.07ms`.
- `reply_markup_clear_dropped`: count=8, p50=`0.02ms`, p95=`0.07ms`, p99=`0.07ms`, max=`0.07ms`.
- `catalog_cache_refreshed_after_commit`: count=2, p50=`5.25ms`, p95=`8.35ms`, p99=`8.35ms`, max=`8.35ms`.
- El slow path agregado esta en background externo/LLM/API Telegram; no en `webhook_response_ready`.

Pruebas:
- [x] Pasar logs reales por `core/scripts/analyze_telegram_latency.py`.
- [x] Confirmar agrupacion por trace.
- [x] Confirmar slowest stage.
- [x] Confirmar cache version y age.
- [x] Confirmar visibilidad de `sendMessage` y `answerCallbackQuery`.

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
