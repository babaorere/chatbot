# Plan de optimizacion de latencia y cache

## Estado actual

- Proyecto activo: `/home/manager/Sync/python_proyects/chatbot`.
- SSOT editable: este repositorio.
- Producto: single-tenant, multi-user. No introducir flujos publicos multi-tenant.
- PostgreSQL sigue siendo la fuente de verdad transaccional.
- Cache en memoria se usa solo para navegacion/catalogo y prompts no transaccionales.
- Confirmacion de carrito, checkout, stock final, precio final y pedidos deben seguir consultando PostgreSQL dentro de la transaccion.

## Regla de plan vivo

Este archivo es un plan operativo vivo, no un contrato rigido.

- [ ] Si durante la ejecucion aparece evidencia tecnica que contradice un paso, actualizar este plan antes o junto con el cambio de codigo.
- [ ] Si los logs muestran que el cuello de botella esta en otro tramo, reordenar el checklist para atacar primero el cuello real.
- [ ] Si un paso se vuelve innecesario, marcarlo como eliminado o reemplazado y dejar la razon tecnica.
- [ ] Si aparece una dependencia previa, insertarla antes del paso que depende de ella.
- [ ] Si una optimizacion compromete correctness, seguridad, trazabilidad o consistencia transaccional, eliminarla o redisenarla.
- [ ] Si aparece un issue durante la ejecucion, no degradarlo a nota o follow-up: agregarlo al checklist y resolverlo.
- [ ] Si un test falla por un contrato real roto, corregir el codigo o el plan; no normalizar el fallo.
- [ ] Si un test falla por un supuesto obsoleto del test, actualizar el test y documentar implicitamente el nuevo contrato en la asercion.
- [ ] Si una decision depende del runtime real (un proceso vs multiples workers, Redis disponible, ARQ activo), verificar el runtime antes de implementar.
- [ ] Cada modificacion relevante del plan debe preservar el principio: PostgreSQL es la verdad transaccional; cache acelera lectura no transaccional.

## Ya implementado

- Logs de timing por `trace_id` en Telegram:
  - `[telegram_timing] trace=tg:<user_id>:<update_id> ...`
  - `[telegram_api_timing] trace=tg:<user_id>:<update_id> ...`
- Medicion de:
  - parseo del webhook
  - lock Redis/local
  - scheduling de background task
  - tiempo hasta respuesta HTTP del webhook
  - inicio y fin del background
  - lectura FSM
  - routing de input
  - validacion de callback
  - render de menu
  - envio a Telegram
  - persistencia FSM
  - ejecucion del use case/LLM
- `answerCallbackQuery` y limpieza de markup se ejecutan fuera del path bloqueante cuando aplica.
- `CatalogSnapshot` atomico en memoria con:
  - `categories`
  - `products_by_category`
  - `products_by_id`
  - `loaded_at`
  - `version`
- Prompts de compra (`render_quantity_prompt`, `render_confirmation_prompt`) usan `products_by_id` cacheado cuando existe.
- Resolucion de categoria por texto usa cache antes de caer a DB.
- Invalidacion/refresco explicito del snapshot despues de mutaciones confirmadas:
  - crear/actualizar/eliminar/importar productos
  - crear/renombrar/eliminar categorias
- Tests focalizados existentes:
  - cache de catalogo
  - invalidacion de cache
  - webhook Telegram
  - compra Telegram
  - jobs Telegram
  - e2e frontend Playwright

## Como medir antes de cambiar mas

1. Ejecutar una conversacion real o simulada con `update_id` controlado.
2. Buscar logs por `trace`:

```bash
rg "trace=tg:<user_id>:<update_id>" logs/ -S
```

3. Si los logs salen por stdout/systemd/Docker:

```bash
docker compose logs -f api | rg "telegram_timing|telegram_api_timing|telegram_cache"
```

4. Interpretacion rapida:
   - `webhook_response_ready` alto: problema antes de responder a Telegram.
   - `background_started_after_webhook` alto: `BackgroundTasks` o proceso saturado.
   - `initial_fsm_context_loaded` alto: Redis/FSM lento.
   - `callback_validated` alto: demasiadas lecturas FSM secuenciales.
   - `callback_menu_plan_rendered` alto: render hace DB o trabajo pesado.
   - `telegram_send_message_done` alto: roundtrip Telegram/sendMessage.
   - `[telegram_api_timing] method=answerCallbackQuery` alto: Telegram API o red.
   - `process_message_uc_done` alto: LLM/use case.
   - `[telegram_cache] version=0`: cache no fue primado.
   - `[telegram_cache] age_seconds` excesivo tras cambios admin: invalidacion no ocurrio.

## Checklist siguiente

### 1. Consolidar helper de analisis de logs

- [x] Crear script `core/scripts/analyze_telegram_latency.py`.
- [x] Entrada: archivo de logs o stdin.
- [x] Parsear lineas con:
  - `[telegram_timing]`
  - `[telegram_api_timing]`
  - `[telegram_cache]`
- [x] Agrupar por `trace`.
- [x] Mostrar tabla por trace con:
  - `webhook_response_ready`
  - `background_started_after_webhook`
  - `webhook_to_background_finished`
  - `initial_fsm_context_loaded`
  - `callback_validated`
  - `callback_menu_plan_rendered`
  - `telegram_send_message_done`
  - `process_message_uc_done`
  - llamadas `sendMessage`
  - llamadas `answerCallbackQuery`
- [x] Marcar en salida el mayor tramo por trace.
- [x] Salida esperada ejemplo:

```text
trace=tg:777002:9002 total_bg=2.44ms webhook_ack=0.71ms slowest=telegram_sendMessage:180.21ms
```

- [x] Agregar test unitario del parser con logs de ejemplo.
- [x] No agregar dependencias externas; usar stdlib (`re`, `argparse`, `dataclasses`).

### 2. Reducir lecturas FSM secuenciales en callbacks

- [ ] Revisar en `core/controllers/telegram_controller.py` el bloque de callback.
- [ ] Actualmente puede llamar en secuencia:
  - `fsm.get_state()`
  - `fsm.get_active_menu_id()`
  - `fsm.get_fsm_version()`
  - `fsm.get_menu_stack()`
  - `fsm.get_context()` en ramas posteriores
- [ ] Crear metodo en `TelegramConversationFSM` para cargar una sola vez estado/contexto/menu metadata.
- [ ] Nombre sugerido:

```python
async def get_runtime_snapshot(self) -> TelegramFSMRuntimeSnapshot:
    ...
```

- [ ] Snapshot sugerido:
  - `state`
  - `context`
  - `active_menu_id`
  - `fsm_version`
  - `menu_stack`
  - `menu_scope`
  - `expected_input`
  - `allow_numeric_input`
- [ ] Usar el snapshot solo para lecturas dentro del turno.
- [ ] Mantener escrituras FSM serializadas y explicitas.
- [ ] No paralelizar escrituras.
- [ ] Tests:
  - callback valido por `active_menu_id`
  - callback valido por version
  - callback expirado
  - seleccion numerica legacy
  - `menu:back`
- [ ] Validar que bajan tiempos de:
  - `callback_validated`
  - `menu_stack_loaded`

### 3. Invalidacion distribuida si hay mas de un worker

- [ ] Confirmar runtime real:
  - un proceso unico: no hace falta Redis pub/sub todavia
  - multiples workers uvicorn/gunicorn/container replicas: necesario
- [ ] Si hay multiples procesos, implementar version distribuida.
- [ ] Opcion minima recomendada:
  - Redis key: `chatbot:catalog:snapshot_version`
  - En cada mutacion admin:
    - refrescar snapshot local
    - incrementar version Redis
  - En cada webhook:
    - leer version Redis con TTL local corto o cada N segundos
    - si version remota > version local, refrescar snapshot local
- [ ] Evitar pub/sub inicialmente si no es necesario.
- [ ] No bloquear webhook en Redis si Redis esta caido salvo que el sistema ya dependa de Redis para sesiones.
- [ ] Si Redis es obligatorio en produccion, fallar explicitamente ante error.
- [ ] Tests:
  - version remota mayor dispara refresh
  - version remota igual no refresca
  - fallo Redis se propaga o se maneja segun contrato de runtime

### 4. Prewarm durante tiempos idle del cliente

- [ ] En `/start` y menu principal, disparar tareas no criticas despues de enviar respuesta.
- [ ] Prewarm permitido:
  - refrescar catalog snapshot si `version=0`
  - construir markup de categorias
  - construir detalle de categorias mas usadas
  - precargar business config estable
- [ ] No prewarm de:
  - carrito
  - pedidos
  - stock final transaccional
  - checkout
- [ ] Usar tareas no bloqueantes con logging de excepcion.
- [ ] Si el prewarm afecta correctness, no hacerlo en background.
- [ ] Tests:
  - `/start` responde aunque prewarm falle si es puramente optimizacion
  - fallo de prewarm queda logueado
  - no cambia FSM ni carrito

### 5. Limitar concurrencia no critica con semaforos

- [ ] Identificar tareas no criticas:
  - cleanup de reply markup
  - prewarm
  - metricas/analisis
- [ ] Crear semaforo por tipo de tarea si hay riesgo de acumulacion.
- [ ] No usar semaforo para bloquear respuesta principal.
- [ ] Si no se puede adquirir semaforo:
  - para tareas cosmeticas: registrar y saltar
  - para tareas de correctness: no saltar; usar ARQ o fallar
- [ ] No introducir locks globales que bloqueen todos los usuarios.
- [ ] Mantener lock por usuario para preservar orden de conversacion.
- [ ] Tests:
  - dos usuarios distintos no se bloquean entre si
  - dos updates del mismo usuario mantienen orden o rechazan duplicado
  - tareas cosmeticas pueden dropearse sin romper UX contractual

### 6. Mover limpieza cosmetica completamente a ARQ cuando Redis este disponible

- [ ] Revisar `_defer_clear_reply_markup`.
- [ ] Hoy ya usa `JobDispatcher`.
- [ ] Confirmar que no se espera en path critico.
- [ ] Validar que `answerCallbackQuery` siempre se dispara antes o independiente de limpieza.
- [ ] Si Redis/ARQ no esta disponible:
  - decidir contrato: fallar o fallback in-process
  - segun reglas actuales, cleanup cosmetico puede ser best-effort; correctness no
- [ ] Tests:
  - `answerCallbackQuery` no espera cleanup
  - job recibe solo payload serializable
  - job propaga `trace_id`, `user_id`, `message_id`

### 7. Cache estable de configuracion de negocio

- [ ] Revisar `BusinessConfigService(db).get_config()` en rutas calientes.
- [ ] Mantener cache solo para datos estables:
  - nombre negocio
  - horarios
  - direccion
  - servicios
  - estimated_attention_minutes si se usa solo en mensaje
  - human_agent_available con TTL corto o invalidacion explicita
- [ ] No cachear:
  - pedidos
  - carrito
  - stock transaccional
  - precio final de checkout
- [ ] Crear snapshot separado:

```python
BusinessConfigSnapshot(...)
```

- [ ] Invalidar en `update_profile`.
- [ ] Tests:
  - update profile refresca snapshot
  - lectura caliente no consulta DB
  - checkout sigue usando DB si el dato afecta contrato final

### 8. Pre-render de menus estaticos

- [ ] Pre-renderizar:
  - menu principal
  - menu categorias
  - detalle de categoria por slug
- [ ] Versionar junto con `CatalogSnapshot.version`.
- [ ] No incluir datos por usuario en pre-render global.
- [ ] No pre-renderizar:
  - carrito
  - pedidos
  - menus con estado de usuario
- [ ] Enviar siempre pasando por `send_menu_message` para inyectar version FSM.
- [ ] Tests:
  - cambio de catalogo invalida pre-render
  - menu por usuario no filtra datos incorrectos
  - botones mantienen callback_data esperado

### 9. Revisar rutas que hacen DB en render de menus

- [ ] `render_promotions_menu`
- [ ] `render_best_sellers_menu`
- [ ] `render_favorites_menu`
- [ ] `render_cart_menu`
- [ ] `render_orders_menu`
- [ ] Clasificar:
  - estatico/global cacheable
  - dinamico/usuario no cacheable
  - transaccional DB obligatorio
- [ ] Promociones/favoritos pueden cachearse si vienen de config estable.
- [ ] Mas vendidos puede requerir DB o snapshot calculado periodicamente.
- [ ] Carrito y pedidos deben seguir DB.
- [ ] Tests:
  - promociones cacheadas no consultan DB tras prewarm
  - carrito sigue consultando DB
  - pedidos sigue consultando DB

### 10. Validacion runtime real

- [ ] Ejecutar backend local controlado:

```bash
cd core
APP_ENV=production SESSION_BACKEND=memory TELEGRAM_BOT_TOKEN=e2e-token LOG_LEVEL=INFO \
uv run uvicorn main:app --host 127.0.0.1 --port 8011
```

- [ ] Enviar webhook liviano sin llamada externa a Telegram:

```bash
curl -sS -w '\nhttp_code=%{http_code} total_ms=%{time_total}\n' \
  -X POST http://127.0.0.1:8011/telegram/webhook/e2e-token \
  -H 'content-type: application/json' \
  -d '{"update_id":9002,"callback_query":{"from":{"id":777002},"message":{"chat":{"id":777002},"date":1},"data":"menu:stock#999"}}'
```

- [ ] Verificar logs:
  - `webhook_response_ready`
  - `background_started_after_webhook`
  - `webhook_to_background_finished`
  - `[telegram_cache] version=... age_seconds=...`
- [ ] Detener proceso temporal al terminar.

### 11. Gates obligatorios despues de cada fase

- [ ] Lint y formato:

```bash
cd core
uv run ruff check <archivos_tocados>
uv run ruff format --check <archivos_tocados>
```

- [ ] Tests backend focalizados:

```bash
cd core
uv run pytest \
  tests/test_catalog_cache_invalidation.py \
  tests/test_telegram_catalog_cache.py \
  tests/test_telegram_service.py \
  tests/test_telegram_jobs.py \
  tests/test_telegram_webhook_validation.py \
  tests/test_telegram_purchase_flow.py \
  tests/test_telegram_hybrid_menu.py \
  tests/test_telegram_conversational_e2e.py \
  tests/test_telegram_post_checkout.py \
  -q
```

- [ ] E2E frontend:

```bash
npm run test:e2e
```

- [ ] Si hay cambios de background jobs:
  - validar worker ARQ
  - validar heartbeat
  - validar payload serializable

## Reglas de no regresion

- [ ] No mover respuesta inmediata del usuario a cola durable.
- [ ] No usar cache como verdad para checkout, stock final o pedidos.
- [ ] No introducir `except: pass`.
- [ ] No degradar errores a warnings si afectan correctness.
- [ ] No bloquear todo el proceso por tareas cosmeticas.
- [ ] No crear APIs publicas multi-tenant.
- [ ] No agregar dependencias si stdlib/proyecto existente resuelve.
- [ ] No crear arquitectura paralela si se puede extender la ruta actual.
- [ ] No dejar tests que dependan de Redis real salvo que sean integration tests marcados.

## Orden recomendado de ejecucion

1. Crear `analyze_telegram_latency.py`.
2. Reducir lecturas FSM secuenciales con snapshot FSM.
3. Implementar invalidacion distribuida solo si hay multiples workers.
4. Agregar prewarm idle no critico.
5. Agregar semaforos para tareas no criticas si los logs muestran acumulacion.
6. Cachear configuracion estable del negocio.
7. Pre-renderizar menus estaticos versionados.
8. Revisar promociones/favoritos/mas vendidos.
9. Repetir mediciones reales y comparar antes/despues.
