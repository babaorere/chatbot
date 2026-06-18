# Plan: Conversión Multi-Tenant → Single-Tenant

**Fecha:** 2026-06-17
**Estado:** Completado

## Contexto

El proyecto `botilleria-core` fue diseñado como multi-tenant con:
- Row-Level Security (RLS) en PostgreSQL
- Resolución dinámica de tenant por canal (Telegram token → ChannelRoute → Tenant)
- `tenant_id` en todos los modelos (User, Conversation, Message, Product, KB)
- `TenantResolverMiddleware` con headers `X-Tenant-ID`
- `TenantService` + `ChannelRouteRepository` para resolución
- `TenantLLMConfig` dinámico por tenant
- Panel admin + portal tenant self-service
- Docker Compose con DB compartida (`shared_db_net`)

## Decisión de diseño

**VPS completo aislado por tenant**: cada VPS tiene su propio PostgreSQL, Redis, API, Nginx.
**Admin centralizado en app separada**: la gestión multi-tenant será otra app que llama a las APIs de cada VPS.

## Principios de la conversión

1. **Eliminar RLS** — no se necesita si cada VPS tiene su propia DB
2. **Eliminar resolución de tenant** — solo existe un "tenant" (el dueño del VPS)
3. **tenant_id → eliminado de modelos** — todas las tablas dejan de tener la columna
4. **Tenant model → BusinessConfig** — la tabla `tenants` se convierte en una única fila de config de negocio
5. **ChannelRoute → eliminado** — el canal (Telegram token) se configura en `.env`/settings
6. **Controllers simplificados** — sin `X-Tenant-ID`, sin portal admin (irá en app separada)
7. **LLM config desde settings** — no desde DB dinámica; cada VPS tiene su modelo configurado en env

## Cambios por capa

### 1. `config/database.py`
- ELIMINAR: `set_tenant_context()`, `reset_tenant_context()`, `enable_rls_on_startup()`
- MANTENER: engines, session factories, `get_db()`, `safe_transaction`

### 2. `middleware/tenant_resolver.py`
- ELIMINAR archivo completo
- Actualizar `middleware/__init__.py` para remover export

### 3. `models/tenant.py`
- RENOMBRAR a `models/business_config.py`
- Clase `BusinessConfig` con campos: `name`, `config` (JSON), `email`, `phone`, `address`, `city`, `website`, `logo_url`, `business_hours`
- ELIMINAR: `slug`, `status`, `get_instruction()`, `get_model()`, `get_api_key()`
- Única fila — singleton pattern con ID=1

### 4. `models/channel_route.py`
- ELIMINAR archivo completo

### 5. Modelos con `tenant_id`
- **User**: eliminar columna `tenant_id` y FK. UniqueConstraint → `(external_id, platform)` (sin tenant_id)
- **Conversation**: eliminar `tenant_id` y FK
- **Message**: eliminar `tenant_id` y FK
- **Product**: eliminar `tenant_id` y FK
- **KnowledgeBase**: eliminar `tenant_id` y FK

### 6. Repositories
- **TenantRepository** → `BusinessConfigRepository` (singleton get/set)
- **ChannelRouteRepository** → ELIMINAR
- **UserRepository**: eliminar `tenant_id` de `find_by_external_id_and_platform()`, `find_by_tenant_id()`, `exists_by_external_id_and_platform()`
- **ConversationRepository**: eliminar `tenant_id` de todos los métodos
- **MessageRepository**: sin cambios (ya no filtra por tenant)
- **ProductRepository**: eliminar `tenant_id` de todos los métodos
- **KBRepository**: eliminar `tenant_id` de todos los métodos (FTS tampoco)

### 7. Services
- **TenantService** → `BusinessConfigService` (get/update config del negocio)
- **UserService**: eliminar `tenant_id` del constructor
- **ConversationService**: eliminar `tenant_id` del constructor
- **ProductService**: eliminar `tenant_id` del constructor
- **KBService**: eliminar `tenant_id` del constructor
- **AgentFactory**: simplificar (no necesita tenant_id)
- **SessionServiceFactory**: sin cambios

### 8. Application layer
- **ProcessMessageUseCase**:
  - ELIMINAR `_resolve_tenant()`
  - ELIMINAR `set_tenant_context()`
  - ELIMINAR `tenant_id` de `_get_or_create_user()` y `_ensure_conversation()`
  - Usar config de settings para LLM (no desde DB)
  - Simplificar constructor: solo `db`, `llm_provider`, `rag_provider`
- **ProcessMessageCommand**: ELIMINAR `channel_identifier` (no hay resolución por canal)
- **ProcessMessageResult**: ELIMINAR `tenant_slug`
- **ILLMProvider**: eliminar `TenantLLMConfig`, usar `Settings` directamente
- **IRAGProvider**: eliminar `tenant_id` de `build_context()`

### 9. Domain
- **TenantLLMConfig** → ELIMINAR (LLM config viene de `settings.py`)
- **domain/tenant/** → ELIMINAR directorio completo

### 10. Infrastructure
- **ADKLLMProvider**:
  - Construir Agent/Runner directamente desde `settings` (no desde `TenantLLMConfig`)
  - ELIMINAR `RunnerRegistry` (no hay multi-tenant, 1 runner por proceso)
  - ELIMINAR `APIKeyResolver` (la key viene de settings/env)
- **KBRAGProvider**: eliminar `tenant_id` de `build_context()`
- **telegram_fsm.py**: simplificar (no necesita resolver tenant desde DB)

### 11. Agents
- **root_agent.py**: Leer model/api_key/instruction desde `settings` (no desde tenant.config dinámico)
- **constants.py**: Mantener pero derivar desde settings

### 12. Controllers
- **tenant_controller.py** → ELIMINAR (admin de tenants va en app separada)
- **tenant_portal_controller.py** → **business_config_controller.py** (CRUD de config local, sin X-Tenant-ID)
- **admin_controller.py** → SIMPLIFICAR: solo health/metrics local, sin gestión multi-tenant
- **chat_controller.py**: Eliminar `X-Tenant-ID`, simplificar comando
- **telegram_controller.py**: Eliminar resolución de tenant por token
- **session_controller.py**: Simplificar (sin tenant_id en sesiones)
- **health_controller.py**: Sin cambios

### 13. DTOs
- **tenant_request.py** → **config_request.py** (solo BusinessConfigUpdate, Product CRUD, KB CRUD)
- **tenant_response.py** → **config_response.py**
- ELIMINAR: `TenantCreateRequest`, `ChannelRouteCreateRequest`

### 14. Exceptions
- **tenant_exceptions.py** → SIMPLIFICAR: eliminar `TenantNotFoundError`, `TenantInactiveError`, `ChannelRouteNotFoundError`, `TenantResolutionError`
- Mantener solo las que apliquen (ej: `BusinessConfigNotFoundError` si aplica)

### 15. Docker
- **docker-compose.yml**: Eliminar `shared_db_net`, tunnel token hardcoded como env var, DB propia
- **docker-compose.botilleria.yml**: Simplificar sin shared DB
- **docker-compose.prod.yml**: Review

### 16. Settings
- Agregar: `BUSINESS_NAME`, `BUSINESS_HOURS`, `BUSINESS_ADDRESS`, etc.
- LLM config ya está — confirmar

## Archivos a_eliminar

1. `models/channel_route.py`
2. `repositories/channel_route_repository.py`
3. `middleware/tenant_resolver.py`
4. `domain/tenant/` (directorio completo)
5. `controllers/tenant_controller.py`
6. `controllers/tenant_portal_controller.py`
7. `controllers/admin_controller.py` (versión multi-tenant)
8. `infrastructure/llm/runner_registry.py`
9. `infrastructure/llm/key_resolver.py`
10. `services/tenant_service.py`
11. `repositories/tenant_repository.py`
12. `services/session_service_factory.py` (redundante si solo hay un backend)

## Archivos a_crear

1. `models/business_config.py`
2. `repositories/business_config_repository.py`
3. `services/business_config_service.py`
4. `controllers/business_config_controller.py`
5. `controllers/admin_controller.py` (versión simplificada)
6. `dtos/request/config_request.py`
7. `dtos/response/config_response.py`
8. `exceptions/config_exceptions.py`

## Orden de ejecución

1. Models (quitar tenant_id, crear BusinessConfig)
2. Repositories (adaptar queries)
3. Services (quitar tenant_id)
4. Config/database (quitar RLS)
5. Domain + Application layer (simplificar)
6. Infrastructure (ADK provider, RAG)
7. Controllers (simplificar/eliminar)
8. Middleware (eliminar tenant resolver)
9. DTOs (renombrar/simplificar)
10. Exceptions (limpiar)
11. Settings (agregar business config)
12. Main + Container (wiring)
13. Tests (actualizar)
14. Docker (simplificar compose)
15. AGENTS.md (actualizar)
