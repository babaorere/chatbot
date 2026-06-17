# Redis Session Design

## Contexto

El proyecto usaba `InMemorySessionService` en dos puntos:

- `services/llm_service.py`
- `agents/root_agent.py`

Eso dejaba la memoria conversacional aislada por proceso. En despliegue multiworker la sesión no era compartida.

## Criterios de diseño

- mantener contrato ADK real
- no mezclar Redis con datos transaccionales del negocio
- aislar estado por `app_name`, `user_id` y `session_id`
- soportar múltiples workers
- evitar pérdidas por carreras concurrentes
- mantener implementación simple y auditable

## Alternativas evaluadas

### 1. Mantener `InMemorySessionService`

Descartado.

Razones:

- no persiste reinicios
- no comparte estado entre workers
- no escala horizontalmente

### 2. Usar `DatabaseSessionService`

No elegida para esta fase.

Razones:

- el objetivo del cambio era Redis como working memory
- PostgreSQL ya tiene responsabilidad transaccional y RLS del negocio
- Redis encaja mejor para latencia baja, locks y TTL

### 3. Implementar `RedisSessionService`

Elegida.

Razones:

- respeta la interfaz oficial `BaseSessionService`
- permite compartir sesiones entre workers
- habilita locking distribuido
- mantiene PostgreSQL como fuente de verdad del negocio

## Principios aplicados

### DRY

- una sola factoría de sesión para la app y para el agente alterno

### SOLID

- `RedisSessionService` tiene una responsabilidad única: persistencia y recuperación de sesiones ADK
- `config/redis.py` encapsula la creación del cliente
- `LLMService` deja de decidir cómo se persisten las sesiones

### KISS

- sesiones como JSON
- `app_state` y `user_state` como hashes Redis
- `SCAN` por prefijo para `list_sessions`
- lock por sesión

## Riesgos conocidos

- no se agregó todavía rate limiting Redis
- no se agregó caché RAG Redis
- no hay prueba de integración automática con un Redis real en esta máquina

## Validaciones implementadas

- pruebas unitarias de `RedisSessionService`
- `ruff`
- `pytest`
- `pip install -e ".[dev]"` corregido vía metadata setuptools

## Resultado esperado

- misma sesión visible desde múltiples workers
- sesiones resistentes a reinicios del proceso
- continuidad conversacional consistente en VPS multiworker
