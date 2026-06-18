# Plan: Conversión Multi-Tenant → Single-Tenant

**Fecha:** 2026-06-17  
**Estado:** En ejecución  
**Nombre:** `single-tenant-conversion`

## Contexto

El proyecto `botilleria-core` fue diseñado como multi-tenant con:
- Row-Level Security (RLS) en PostgreSQL
- Resolución dinámica de tenant por canal: Telegram token → `ChannelRoute` → `Tenant`
- `tenant_id` en todos los modelos principales: `User`, `Conversation`, `Message`, `Product`, `KnowledgeBase`
- `TenantResolverMiddleware` con headers `X-Tenant-ID`
- `TenantService` + `ChannelRouteRepository` para resolución
- `TenantLLMConfig` dinámico por tenant
- Panel admin + portal tenant self-service
- Docker Compose con DB compartida mediante `shared_db_net`

## Decisión de diseño

**VPS completo aislado por tenant:**
- Cada tenant tendrá su propio VPS.
- Cada VPS tendrá su propio PostgreSQL, Redis, API, Nginx y datos.
- No habrá DB compartida entre tenants.

**Admin centralizado en app separada:**
- La gestión multi-tenant será una app separada.
- Esa app llamará a la API de cada VPS para gestión, métricas y monitoreo.
- El proyecto actual debe quedar como runtime single-tenant.

## Objetivo del proyecto convertido

El sistema debe funcionar como una instalación independiente por negocio:
- Un negocio por VPS.
- Una base de datos propia.
- Un canal Telegram propio.
- Una configuración local propia.
- Sin RLS.
- Sin resolución de tenant.
- Sin `tenant_id`.
- Sin multi-tenant runtime.

## Principios de conversión

1. **Eliminar RLS**
   - No se necesita aislamiento por DB si cada VPS es aislado.

2. **Eliminar resolución de tenant**
   - Solo existe un negocio local.

3. **Eliminar `tenant_id` de los modelos**
   - Todas las tablas principales deben quedar sin `tenant_id`.

4. **Convertir `Tenant` en `BusinessConfig`**
   - La tabla `tenants` se reemplaza por una configuración única del negocio.

5. **Eliminar `ChannelRoute`**
   - El canal se configura en variables de entorno, por ejemplo `TELEGRAM_BOT_TOKEN`.

6. **Configuración LLM desde settings**
   - El modelo, API key e instrucción vendrán de `.env`/settings.
   - No desde DB dinámica por tenant.

7. **RAG limitado a preguntas generales**
   - El RAG no debe usarse para productos, stock ni precios.
   - Stock y precios deben venir de herramientas/productos reales.

## Regla crítica de RAG para ventas

El RAG debe limitarse exclusivamente a preguntas generales del negocio.

### RAG permitido

El RAG solo debe activarse para preguntas sobre:
- Horario de atención.
- Zonas de atención.
- Formas de pago.
- Servicio delivery.
- Información general del servicio.
- Información institucional no dinámica.

Ejemplos permitidos:
- `"¿Cuál es el horario de atención?"`
- `"¿En qué comunas hacen delivery?"`
- `"¿Qué zonas cubren?"`
- `"¿Aceptan transferencia?"`
- `"¿Aceptan efectivo?"`
- `"¿Hacen delivery?"`
- `"¿Qué métodos de pago tienen?"`
- `"¿Están abiertos ahora?"`

### RAG prohibido

El RAG debe bloquearse explícitamente para:
- Stock.
- Disponibilidad.
- Precios.
- Promociones de productos.
- Catálogo.
- Productos específicos.
- Compras.
- Cotizaciones.
- Consultas que impliquen inventario o venta real.

Ejemplos prohibidos:
- `"¿Tienen pisco sour?"`
- `"¿Hay cerveza Kunstmann?"`
- `"¿Cuánto vale el vino Santa Carolina?"`
- `"¿Precio del pisco Control?"`
- `"¿Tienen whisky Johnnie Walker?"`
- `"¿Está disponible la cerveza de trigo?"`
- `"Quiero comprar un pisco"`
- `"Cotízame dos vinos y una cerveza"`

### Implementación requerida para RAG

1. **Clasificador de intención**
   - Crear `services/message_classifier.py` o `services/rag_policy.py`.
   - Debe clasificar mensajes como:
     - `general_service`
     - `product_sales`
     - `unknown`
   - El use case solo debe llamar a RAG si la intención es `general_service`.

2. **Bloqueo defensivo en `KBRAGProvider`**
   - `KBRAGProvider.build_context()` también debe bloquear RAG si detecta producto/venta.
   - No se debe depender solo del use case.

3. **Prompt explícito del LLM**
   - El prompt debe indicar:
     - Para preguntas generales, puede usar el contexto RAG.
     - Para stock, precios, catálogo, compras o productos, debe usar herramientas reales.
     - Nunca debe inventar stock ni precio.
     - Si no puede consultar inventario, debe decir que no puede confirmar.

4. **Categorías de KB**
   - La KB debe tener categorías claras:
     - `horarios`
     - `zonas_atencion`
     - `formas_pago`
     - `delivery`
     - `servicios`
   - Evitar categoría `productos` para RAG.

5. **Tests de protección**
   - Agregar tests unitarios para:
     - `"¿tienen pisco sour?"` → RAG = `None`
     - `"cuánto vale el vino santa carolina?"` → RAG = `None`
     - `"¿hacen delivery?"` → RAG permitido
     - `"¿cuál es el horario de atención?"` → RAG permitido
     - `"¿en qué comunas hacen delivery?"` → RAG permitido
     - `"¿aceptan transferencia?"` → RAG permitido

6. **Herramientas separadas**
   - Stock y precios deben venir de herramientas/productos reales.
   - `consultar_stock()` debe consultar DB.
   - `consultar_precio()` debe consultar DB.
   - RAG nunca debe ser fuente de verdad para productos.

## Cambios por capa

### 1. `config/database.py`

Eliminar:
- `set_tenant_context()`
- `reset_tenant_context()`
- `enable_rls_on_startup()`

Mantener:
- Engines.
- Session factories.
- `get_db()`.
- `safe_transaction`.

### 2. `middleware/tenant_resolver.py`

Eliminar archivo completo.

Actualizar:
- `middleware/__init__.py` para remover export.

### 3. `models/tenant.py`

Reemplazar por:
- `models/business_config.py`

Nueva clase:
- `BusinessConfig`

Campos:
- `name`
- `email`
- `phone`
- `address`
- `city`
- `website`
- `logo_url`
- `business_hours`

Eliminar:
- `slug`
- `status`
- `config`
- `get_instruction()`
- `get_model()`
- `get_api_key()`

Patrón:
- Única fila por instalación.

### 4. `models/channel_route.py`

Eliminar archivo completo.

### 5. Modelos con `tenant_id`

Eliminar `tenant_id` de:
- `User`
- `Conversation`
- `Message`
- `Product`
- `KnowledgeBase`

Ajustes:
- `User`: `UniqueConstraint` debe pasar de `(tenant_id, external_id, platform)` a `(external_id, platform)`.
- `Conversation`: `session_id` sigue siendo único global dentro de la DB local.
- `Product`: debe quedar listo para ventas reales.
- `KnowledgeBase`: debe quedar sin tenant.

### 6. Repositories

Reemplazar:
- `TenantRepository` → `BusinessConfigRepository`

Eliminar:
- `ChannelRouteRepository`

Adaptar:
- `UserRepository`
- `ConversationRepository`
- `MessageRepository`
- `ProductRepository`
- `KBRepository`

Reglas:
- Eliminar filtros por `tenant_id`.
- Mantener búsquedas locales.
- `KBRepository.search_fts()` no debe aceptar `tenant_id`.
- `KBRepository.search_fts()` debe permitir filtrar por categoría general.

### 7. Services

Reemplazar:
- `TenantService` → `BusinessConfigService`

Adaptar:
- `UserService`
- `ConversationService`
- `ProductService`
- `KBService`

Eliminar `tenant_id` de constructores.

Crear:
- `services/message_classifier.py` o `services/rag_policy.py`

Responsabilidad:
- Clasificar si una consulta puede usar RAG.
- Bloquear consultas de productos/ventas.

### 8. Application layer

Actualizar `ProcessMessageUseCase`:

Eliminar:
- `_resolve_tenant()`
- `set_tenant_context()`
- `tenant_id` de `_get_or_create_user()`
- `tenant_id` de `_ensure_conversation()`

Agregar:
- Clasificación de intención antes de llamar a RAG.
- Si es `product_sales`, pasar `rag_context=None`.

Actualizar `ProcessMessageCommand`:
- Eliminar `channel_identifier`.

Actualizar `ProcessMessageResult`:
- Eliminar `tenant_slug`.

Actualizar ports:
- `ILLMProvider`: eliminar `TenantLLMConfig`.
- `IRAGProvider`: eliminar `tenant_id`.

### 9. Domain

Eliminar:
- `domain/tenant/`
- `TenantLLMConfig`

Motivo:
- La configuración LLM vendrá de `settings.py`.

### 10. Infrastructure

Actualizar `ADKLLMProvider`:
- Usar `settings` directamente.
- Eliminar dependencia de `TenantLLMConfig`.
- Inyectar instrucción explícita sobre uso permitido de RAG.
- No crear runners por tenant.

Actualizar `KBRAGProvider`:
- Eliminar `tenant_id`.
- Bloquear consultas de producto/venta.
- Bloquear categorías no permitidas si existen.

Actualizar `telegram_fsm.py`:
- Mantener FSM.
- No necesita resolver tenant.

Eliminar:
- `infrastructure/llm/runner_registry.py`
- `infrastructure/llm/key_resolver.py`

### 11. Agents

Actualizar `root_agent.py`:
- Leer modelo/API key/instrucción desde `settings`.
- No leer desde tenant.config.

Actualizar herramientas:
- `get_current_datetime()` → puede mantenerse.
- `get_botilleria_info()` → debe responder info general.
- `consultar_stock()` → debe consultar DB real.
- `consultar_precio()` → debe consultar DB real.
- `contactar_humano()` → idealmente debe registrar ticket o evento de escalación.

Actualizar `constants.py`:
- Derivar desde `settings` o mantener como defaults.

### 12. Controllers

Eliminar:
- `controllers/tenant_controller.py`
- `controllers/tenant_portal_controller.py`
- Versión multi-tenant de `controllers/admin_controller.py`

Crear:
- `controllers/business_config_controller.py`
- `controllers/admin_controller.py` simplificado

Simplificar:
- `chat_controller.py`
- `telegram_controller.py`
- `session_controller.py`
- `user_controller.py`

Reglas:
- No `X-Tenant-ID`.
- No resolución de tenant.
- No `set_tenant_context()`.
- Admin local solo para configuración y métricas del negocio actual.

### 13. DTOs

Reemplazar:
- `tenant_request.py` → `config_request.py`
- `tenant_response.py` → `config_response.py`

Eliminar:
- `TenantCreateRequest`
- `ChannelRouteCreateRequest`

Mantener/adaptar:
- `ProductCreateRequest`
- `ProductUpdateRequest`
- `KBEntryCreateRequest`
- `KBEntryUpdateRequest`
- `KBSearchRequest`
- `UserCreateRequest`

### 14. Exceptions

Eliminar:
- `TenantNotFoundError`
- `TenantInactiveError`
- `ChannelRouteNotFoundError`
- `TenantResolutionError`

Crear si aplica:
- `BusinessConfigNotFoundError`

### 15. Docker

Actualizar:
- `docker-compose.yml`
- `docker-compose.botilleria.yml`
- `docker-compose.prod.yml`

Reglas:
- Eliminar `shared_db_net`.
- Cada VPS debe levantar su propia DB.
- Cloudflare token debe venir de `.env`, nunca hardcoded.
- No exponer secrets en Docker Compose.

### 16. Settings

Agregar configuración local:
- `BUSINESS_NAME`
- `BUSINESS_EMAIL`
- `BUSINESS_PHONE`
- `BUSINESS_ADDRESS`
- `BUSINESS_CITY`
- `BUSINESS_WEBSITE`
- `BUSINESS_HOURS`
- `TELEGRAM_BOT_TOKEN`

Mantener:
- `OPENROUTER_API_KEY`
- `MODEL_NAME`
- `MODEL_DISPLAY`
- `SESSION_BACKEND`
- `REDIS_URL`

## Archivos a eliminar

1. `models/channel_route.py`
2. `repositories/channel_route_repository.py`
3. `middleware/tenant_resolver.py`
4. `domain/tenant/`
5. `controllers/tenant_controller.py`
6. `controllers/tenant_portal_controller.py`
7. `controllers/admin_controller.py` versión multi-tenant
8. `infrastructure/llm/runner_registry.py`
9. `infrastructure/llm/key_resolver.py`
10. `services/tenant_service.py`
11. `repositories/tenant_repository.py`
12. `services/session_service_factory.py` si queda redundante

## Archivos a crear

1. `models/business_config.py`
2. `repositories/business_config_repository.py`
3. `services/business_config_service.py`
4. `services/message_classifier.py`
5. `controllers/business_config_controller.py`
6. `controllers/admin_controller.py` versión simplificada
7. `dtos/request/config_request.py`
8. `dtos/response/config_response.py`
9. `exceptions/config_exceptions.py`

## Orden de ejecución

1. Models
   - Crear `BusinessConfig`.
   - Eliminar `ChannelRoute`.
   - Quitar `tenant_id` de modelos.

2. Repositories
   - Crear `BusinessConfigRepository`.
   - Adaptar repositorios sin `tenant_id`.

3. Services
   - Crear `BusinessConfigService`.
   - Adaptar services sin `tenant_id`.
   - Crear clasificador RAG.

4. Config/database
   - Eliminar RLS.
   - Simplificar lifespan.

5. Domain + Application
   - Eliminar `TenantLLMConfig`.
   - Simplificar `ProcessMessageUseCase`.
   - Aplicar política RAG.

6. Infrastructure
   - Simplificar `ADKLLMProvider`.
   - Actualizar `KBRAGProvider`.
   - Eliminar runner registry/key resolver.

7. Agents
   - Ajustar tools.
   - Stock/precio desde DB.
   - RAG explícitamente no usado para productos.

8. Controllers
   - Eliminar tenant controllers.
   - Simplificar chat, Telegram, sesiones, usuarios y admin.

9. DTOs
   - Reemplazar tenant DTOs por config DTOs.

10. Exceptions
    - Limpiar tenant exceptions.

11. Settings
    - Agregar configuración local del negocio.

12. Main + Container
    - Wiring final.

13. Tests
    - Actualizar tests existentes.
    - Agregar tests de política RAG.
    - Agregar tests de stock/precio real.

14. Docker
    - Simplificar compose.
    - Eliminar token hardcoded.

15. AGENTS.md
    - Actualizar arquitectura single-tenant.
    - Documentar regla crítica de RAG.

## Criterios de aceptación

El proyecto convertido debe cumplir:

1. Arranca sin multi-tenant.
2. No usa RLS.
3. No usa `tenant_id`.
4. No usa `ChannelRoute`.
5. No usa `X-Tenant-ID`.
6. No usa tenant resolution.
7. Tiene una única configuración local de negocio.
8. Usa DB propia por VPS.
9. RAG solo responde preguntas generales.
10. Stock y precio vienen de DB/herramientas reales.
11. No hay secrets hardcoded.
12. CORS de producción no es `*`.
13. Tests principales pasan.
14. Lint/formateo pasan.

## Riesgos conocidos

1. **Conversión a mitad de camino**
   - Algunos archivos ya fueron modificados y otros no.
   - Hay riesgo de imports rotos hasta completar la migración.

2. **RAG por palabras clave**
   - El clasificador inicial será basado en reglas.
   - Puede fallar con consultas ambiguas.
   - Debe ser defensivo: en duda, no usar RAG para productos.

3. **Stock/precio real**
   - Requiere herramientas bien integradas con DB.
   - El LLM no debe inventar información.

4. **Telegram**
   - Hay que validar token del webhook.
   - FSM en memoria debe pasar a Redis si se usan múltiples workers.

5. **Admin**
   - El admin centralizado debe vivir en otra app.
   - Este proyecto debe exponer solo APIs locales seguras.
