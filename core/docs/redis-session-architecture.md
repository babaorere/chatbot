# Redis Session Architecture

## Objetivo

Mover el estado conversacional de ADK fuera de la memoria del proceso y dejarlo compartido entre workers y futuras réplicas del servicio.

## Problema que corrige

`InMemorySessionService` es válido para desarrollo y pruebas locales, pero no para producción multiworker. En este proyecto el problema era directo:

- `uvicorn` corre con 4 workers.
- cada worker tenía su propio `InMemorySessionService`.
- la memoria conversacional se perdía al cambiar de worker o al reiniciar el proceso.

## Decisión técnica

Se reemplazó la dependencia hardcodeada a `InMemorySessionService` por una factoría de sesión:

- `SESSION_BACKEND=redis` para producción
- `SESSION_BACKEND=memory` solo para fallback explícito en desarrollo

La implementación Redis vive en `services/redis_session_service.py` y sigue el contrato real de `google.adk.sessions.base_session_service.BaseSessionService`.

## Diseño de almacenamiento

### Claves Redis

- `botilleria:adk:v1:session:{app}:{user}:{session}`
- `botilleria:adk:v1:user_state:{app}:{user}`
- `botilleria:adk:v1:app_state:{app}`
- `botilleria:adk:v1:lock:session:{app}:{user}:{session}`

### Qué se guarda

- `session`: objeto `Session` completo de ADK con `events`, `state` de sesión y `last_update_time`
- `user_state`: estado con prefijo `user:`
- `app_state`: estado con prefijo `app:`

### Qué no se guarda

- estado `temp:` de ADK

Ese comportamiento se preserva porque `BaseSessionService.append_event()` ya recorta el delta temporal antes de persistirlo.

## Concurrencia

Se agregó un lock distribuido por sesión.

Uso:

- `create_session`
- `append_event`
- `delete_session`

Esto evita carreras cuando dos workers intentan modificar la misma sesión al mismo tiempo.

## TTL

Solo la sesión tiene TTL renovable por actividad.

- variable: `REDIS_SESSION_TTL_SECONDS`
- default: `86400`

`user_state` y `app_state` no expiran automáticamente para no romper la semántica de estado compartido entre sesiones.

## Integración con la app

### FastAPI

`main.py`:

- crea un cliente Redis por worker en `lifespan`
- valida conectividad con `PING`
- construye `RedisSessionService`
- lo inyecta en `LLMService`
- cierra el cliente al apagar el worker

### Agent path alterno

`agents/root_agent.py` también deja de crear `InMemorySessionService` directamente y pasa por la misma factoría.

## Mejora adicional aplicada

Se corrigió un problema funcional previo en `services/llm_service.py`.

Antes:

- el `Runner` quedaba cacheado por tenant
- el `rag_context` se inyectaba en la instrucción solo al crear el runner
- consultas posteriores del mismo tenant reutilizaban el runner sin refrescar el contexto

Ahora:

- el runner se cachea por tenant y por spec base del agente
- el contexto RAG viaja en el mensaje del turno actual
- cambios de `instruction` o `model` recrean el runner del tenant

## Variables nuevas

- `SESSION_BACKEND`
- `REDIS_URL`
- `REDIS_NAMESPACE`
- `REDIS_SESSION_TTL_SECONDS`
- `REDIS_LOCK_TIMEOUT_SECONDS`
- `REDIS_LOCK_BLOCKING_TIMEOUT_SECONDS`
- `REDIS_HEALTH_CHECK_INTERVAL`
- `REDIS_SOCKET_TIMEOUT_SECONDS`
- `REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS`
- `REDIS_MAX_CONNECTIONS`
- `REDIS_RETRY_ATTEMPTS`

## Recomendación operativa

Producción:

- `SESSION_BACKEND=redis`
- Redis en la misma red privada del servicio
- AOF activado
- healthcheck activo
- monitoreo de memoria y conexiones

Desarrollo local:

- Redis también es recomendable
- `memory` queda solo como fallback explícito para pruebas aisladas
