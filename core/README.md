# Chatbot Core

Backend multi-tenant para atención conversacional de negocios y comercios similares. Expone una API FastAPI para recibir mensajes, resolver a qué tenant pertenece cada conversación, recuperar contexto desde base de conocimiento, consultar un modelo LLM vía OpenRouter y devolver la respuesta al canal de origen.

Está pensado para operar como núcleo de mensajería detrás de integraciones como Telegram, WhatsApp, webchat o flujos externos en Windmill.

## Qué resuelve

- Atiende conversaciones de múltiples negocios desde una sola aplicación.
- Aísla datos por tenant en base de datos con Row-Level Security.
- Mantiene contexto conversacional por `user_id` y `session_id`.
- Permite configurar modelo, instrucciones, canales y contenido de negocio por tenant.
- Soporta respuesta normal y streaming SSE.
- Puede funcionar como backend HTTP para workers externos que reciben webhooks.

## Idea central

Cada mensaje entra por HTTP. El sistema identifica el tenant por header directo o por mapeo de canal, fija el contexto de base de datos para ese tenant, busca información útil en la base de conocimiento, ejecuta el agente ADK contra OpenRouter y devuelve la respuesta.

```mermaid
flowchart LR
    A[Canal de origen<br/>Telegram / WhatsApp / Web / Windmill] --> B[FastAPI]
    B --> C[Resolución de tenant]
    C --> D[RLS en PostgreSQL]
    C --> E[Base de conocimiento]
    E --> F[Contexto RAG]
    D --> G[Usuario y conversación]
    F --> H[LLMService]
    H --> I[Google ADK Runner]
    I --> J[LiteLLM + OpenRouter]
    J --> K[Respuesta]
    K --> B
    B --> A
```

## Flujo de mensaje

```mermaid
flowchart TD
    A[POST /chat o /chat/stream] --> B{Headers de tenant}
    B -->|X-Tenant-ID| C[Resolver tenant directo]
    B -->|X-Platform + X-Channel-Identifier| D[Resolver por canal]
    C --> E[SET app.current_tenant_id]
    D --> E
    E --> F[Buscar contexto en KB]
    F --> G[Crear o recuperar usuario]
    G --> H[Crear o recuperar conversación]
    H --> I[Ejecutar Runner ADK]
    I --> J[Respuesta final o chunks SSE]
```

## Capacidades principales

### Multi-tenant real

- Cada tenant tiene identidad, configuración, canales, productos y KB propios.
- El aislamiento de datos se aplica en PostgreSQL con políticas RLS.
- La resolución del tenant puede venir por UUID explícito o por mapeo de canal.

### Contexto conversacional

- Las sesiones del agente viven en `InMemorySessionService`.
- El contexto se separa por combinación de `user_id` y `session_id`.
- En despliegue con múltiples workers, cada worker mantiene sus propias sesiones en memoria.

### RAG simple y práctico

- La consulta del usuario se usa para buscar entradas relevantes en la KB del tenant.
- Los resultados se agregan al prompt como contexto previo a la generación.
- Si no hay información suficiente, el sistema queda preparado para responder con honestidad y derivar a humano.

### Operación por API

- Respuesta estándar: `POST /chat`
- Streaming SSE: `POST /chat/stream`
- Gestión de tenants, canales y configuración: endpoints `/tenants`, `/admin` y `/tenants/me`
- Historial de sesión y conversaciones: endpoints `/sessions/...`

## Arquitectura del proyecto

```text
chatbot_core/
├── main.py
├── config/         # settings, engines y helpers de DB
├── controllers/    # routers FastAPI
├── middleware/     # request_id y resolución transversal
├── models/         # modelos SQLAlchemy
├── repositories/   # acceso a datos
├── services/       # lógica de negocio, chat, RAG, LLM
├── dtos/           # contratos request/response
├── scripts/        # SQL de apoyo y migraciones manuales
└── tests/          # pruebas unitarias e integración
```

## Componentes clave

### `main.py`

- Inicializa FastAPI.
- Crea tablas al arrancar.
- Habilita políticas RLS sobre tablas multi-tenant.
- Genera un tenant por defecto si la base está vacía.
- Construye un singleton de `LLMService` por proceso.

### `controllers/chat_controller.py`

- Expone `/chat` y `/chat/stream`.
- Resuelve el tenant desde headers.
- Activa el contexto tenant en la sesión SQL.
- Construye contexto RAG y delega a `ChatService`.

### `services/chat_service.py`

- Crea o recupera usuario.
- Crea o recupera conversación.
- Delega la respuesta al `LLMService`.

### `services/llm_service.py`

- Cachea runners ADK por tenant dentro del proceso.
- Usa `LiteLlm` apuntando a OpenRouter.
- Mantiene sesiones con `InMemorySessionService`.

### `services/rag_context_builder.py`

- Busca entradas de KB relevantes.
- Formatea el contexto para inyectarlo en la instrucción del agente.

## Requisitos técnicos

### Runtime

- Python 3.13 recomendado y usado por Docker.
- PostgreSQL recomendado para operación multi-tenant real con RLS.
- OpenRouter API Key obligatoria para producción.

### Dependencias principales

- `fastapi`
- `uvicorn[standard]`
- `sqlalchemy`
- `psycopg2-binary`
- `asyncpg`
- `pydantic` y `pydantic-settings`
- `google-adk[extensions]`
- `litellm`
- `sse-starlette`

## Variables de entorno

| Variable | Requerida | Uso |
|---|---|---|
| `DATABASE_URL` | Sí | Cadena de conexión de PostgreSQL o SQLite para desarrollo |
| `OPENROUTER_API_KEY` | Sí | API key usada por LiteLLM para llamar a OpenRouter |
| `MODEL_NAME` | No | Modelo por defecto |
| `MODEL_DISPLAY` | No | Nombre legible para logs y observabilidad |
| `APP_ENV` | No | `development` o `production` |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `TELEGRAM_BOT_TOKEN` | No | Usado para seed del canal por defecto |
| `DB_ECHO` | No | Traza SQL si el entorno lo expone |

### Ejemplo de `.env`

```env
DATABASE_URL=postgresql://chatbot:chatbot@localhost:5432/chatbot_core
OPENROUTER_API_KEY=<OPENROUTER_API_KEY>
MODEL_NAME=openrouter/nvidia/nemotron-3-super-120b-a12b:free
MODEL_DISPLAY=nemotron-3-super-120b:free
APP_ENV=production
LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=telegram_token_del_canal_principal
```

## Instalación local

### Opción 1: entorno local con `uv`

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env
```

Luego ajusta `.env` y levanta la API:

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Opción 2: instalación con `pip`

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Ejecución con Docker

La imagen actual usa:

- `python:3.13-slim`
- `uvicorn`
- `uvloop`
- `4 workers`

Comando de referencia:

```bash
docker build -t chatbot-core .
docker run --rm -p 8000:8000 --env-file .env chatbot-core
```

La imagen expone `8000/tcp`.

## Arranque esperado

Al iniciar, la aplicación hace lo siguiente:

1. Crea tablas con `Base.metadata.create_all(...)`.
2. Habilita políticas RLS sobre tablas multi-tenant.
3. Inserta un tenant por defecto si no existe ninguno.
4. Crea un `LLMService` singleton por worker.
5. Deja disponible la API para chat, administración y portal de tenant.

## Endpoints principales

### Salud

```http
GET /health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "service": "chatbot-core",
  "version": "1.0.0",
  "multi_tenant": "true",
  "worker_pid": "123"
}
```

### Chat

```http
POST /chat
```

Body:

```json
{
  "user_id": "telegram_12345",
  "platform": "telegram",
  "message": "Hola, tienen pisco?",
  "session_id": "opcional"
}
```

Headers válidos para resolver el tenant:

- `X-Tenant-ID: <uuid>`
- `X-Platform: telegram`
- `X-Channel-Identifier: <token_o_identificador>`

Respuesta:

```json
{
  "session_id": "5f3f8d26-8c62-4a47-b266-9d838c1f6f39",
  "user_id": "telegram_12345",
  "tenant_slug": "el_buen_trago",
  "response": "Sí, tenemos opciones disponibles..."
}
```

### Chat streaming

```http
POST /chat/stream
```

Entrega eventos SSE:

- `chunk`
- `done`

### Administración de tenants

Rutas principales:

- `GET /admin/tenants`
- `POST /admin/tenants`
- `GET /admin/tenants/{tenant_id}`
- `PUT /admin/tenants/{tenant_id}`
- `PATCH /admin/tenants/{tenant_id}/status`
- `PUT /admin/tenants/{tenant_id}/agent`
- `POST /admin/tenants/{tenant_id}/channels`

### Portal del tenant

Rutas principales:

- `GET /tenants/me/profile`
- `PUT /tenants/me/profile`
- `GET /tenants/me/channels`
- `GET /tenants/me/products`
- `POST /tenants/me/products`
- `GET /tenants/me/kb/search`

## Ejemplos de uso con `curl`

### 1. Crear un tenant

```bash
curl -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "chatbot_centro",
    "name": "Negocio Centro",
    "instruction": "Eres el asistente virtual de Negocio Centro.",
    "model": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    "api_key": "<OPENROUTER_API_KEY>"
  }'
```

### 2. Asociar un canal

```bash
curl -X POST http://localhost:8000/tenants/<TENANT_ID>/channels \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "telegram",
    "channel_identifier": "token_bot_telegram"
  }'
```

### 3. Enviar un mensaje con tenant explícito

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: <TENANT_ID>" \
  -d '{
    "user_id": "cliente_001",
    "platform": "telegram",
    "message": "Hola, cuál es su horario?"
  }'
```

### 4. Enviar un mensaje por mapeo de canal

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Platform: telegram" \
  -H "X-Channel-Identifier: token_bot_telegram" \
  -d '{
    "user_id": "cliente_telegram_44",
    "platform": "telegram",
    "message": "Tienen vino tinto?"
  }'
```

### 5. Consultar historial de sesión

```bash
curl "http://localhost:8000/sessions/<SESSION_ID>/history?user_id=cliente_001" \
  -H "X-Tenant-ID: <TENANT_ID>"
```

## Integración con Windmill

El proyecto está preparado para operar como backend HTTP detrás de workers externos.

- El código puede montarse en `/opt/chatbot_core`.
- Los scripts externos pueden llamar a `http://chatbot_core_api:8000/chat`.
- El mapeo `X-Platform` + `X-Channel-Identifier` permite resolver el tenant sin exponer UUIDs.

```mermaid
flowchart LR
    A[Webhook externo] --> B[Worker Windmill]
    B --> C[POST /chat]
    C --> D[Chatbot Core]
    D --> E[OpenRouter]
    D --> F[PostgreSQL]
    D --> C
    C --> B
    B --> A
```

## Modelo de datos operativo

Entidades relevantes:

- `tenants`
- `channel_routes`
- `users`
- `conversations`
- `messages`
- `knowledge_base`
- `products`
- `system_settings`

Relación funcional:

```mermaid
flowchart TD
    A[Tenant] --> B[Channel Routes]
    A --> C[Users]
    A --> D[Knowledge Base]
    A --> E[Products]
    C --> F[Conversations]
    F --> G[Messages]
```

## Seguridad y aislamiento

### Aislamiento por tenant

- La app define `SET app.current_tenant_id = <uuid>` en cada request con contexto tenant.
- PostgreSQL aplica políticas de RLS sobre tablas multi-tenant.
- Esto reduce el riesgo de mezcla de datos entre negocios.

### Límites actuales

- No se observa autenticación fuerte para endpoints administrativos.
- CORS está abierto a cualquier origen.
- Las sesiones del agente viven en memoria de cada worker, no en un backend distribuido.

## Concurrencia y operación real

### Qué ocurre hoy

- La imagen Docker arranca `uvicorn` con `4 workers`.
- Cada worker crea su propio `LLMService`.
- Cada `LLMService` conserva runners ADK y sesiones en memoria del proceso.

### Implicancia práctica

- La aplicación escala bien para I/O de red y llamadas al modelo.
- El historial en memoria no se comparte entre workers.
- Si un mismo usuario cae en otro worker, la memoria conversacional ADK no acompaña ese salto, aunque la conversación en base siga existiendo.

### Para 30 usuarios concurrentes

Sin benchmark formal, y considerando que la mayor latencia vendrá de OpenRouter y no del CPU local, la arquitectura actual es razonable para 30 usuarios concurrentes si:

- la base de datos está sana,
- la red del VPS es estable,
- el proveedor LLM responde con baja latencia,
- y la mezcla de tráfico no exige streaming pesado sostenido.

## Especificaciones de VPS

### Mínimo viable

Pensado para una sola instancia de aplicación y PostgreSQL en el mismo VPS, con tráfico concurrente moderado y margen operativo ajustado.

- 2 vCPU
- 4 GB RAM
- 40 GB NVMe SSD
- 1 Gbps compartido
- Ubuntu 24.04 LTS
- Docker Engine + Compose

Uso recomendado:

- ambiente piloto,
- validación funcional,
- carga real acotada,
- monitoreo cercano.

### Configuración óptima para 30 usuarios concurrentes

Pensada para producción pequeña con margen razonable, 4 workers, PostgreSQL local, logs, picos breves y operación estable.

- 4 vCPU dedicados
- 8 GB RAM
- 80 GB NVMe SSD
- 1 Gbps compartido o mejor
- Ubuntu 24.04 LTS
- Docker Engine + Compose
- swap moderada configurada

Distribución sugerida de recursos:

- App FastAPI + 4 workers: 2.5 a 3.5 GB
- PostgreSQL: 1.5 a 2 GB
- SO, buffers, logs y margen: 2 a 2.5 GB

### Si el tráfico crece o el contexto RAG aumenta

Subir a:

- 8 vCPU
- 16 GB RAM
- 120 GB NVMe SSD

Esto da más espacio para:

- mayor paralelismo,
- respuestas streaming prolongadas,
- más tenants activos,
- búsquedas de KB más frecuentes,
- y colas de requests más estables ante picos.

## Configuración recomendada para VPS

### Sistema operativo

- Ubuntu 24.04 LTS
- zona horaria correcta
- actualizaciones de seguridad activas

### Red y proxy

- Nginx o Caddy delante de Uvicorn
- TLS con Let's Encrypt
- timeouts adecuados para SSE si se usa `/chat/stream`

### Base de datos

- PostgreSQL 15 o superior
- backups diarios
- monitoreo de conexiones y tamaño de tablas

### Observabilidad

- logs centralizados
- health check externo sobre `/health`
- métricas de latencia por endpoint
- alertas por uso de RAM, CPU y errores 5xx

## Despliegue recomendado

### Topología simple

```mermaid
flowchart LR
    A[Internet / Canales] --> B[Reverse Proxy]
    B --> C[Chatbot Core]
    C --> D[PostgreSQL]
    C --> E[OpenRouter]
```

### Orden de despliegue

1. Crear VPS.
2. Instalar Docker y Compose.
3. Configurar `.env`.
4. Levantar PostgreSQL.
5. Construir imagen del backend.
6. Publicar detrás de proxy reverso.
7. Verificar `/health`.
8. Crear tenant y canal inicial.
9. Ejecutar pruebas funcionales de chat y streaming.

## Pruebas y control de calidad

Comandos objetivo del proyecto:

```bash
ruff check .
ruff format .
pytest -q
```

Las pruebas presentes cubren, entre otros casos:

- aislamiento multi-tenant,
- concurrencia multiusuario,
- integración de flujos principales.

## Riesgos operativos a tener presentes

- `create_all()` al arranque no reemplaza una estrategia formal de migraciones.
- `InMemorySessionService` no comparte memoria entre workers ni entre réplicas.
- SQLite sirve para desarrollo, pero no es el camino adecuado para multi-tenant con RLS real.
- Si OpenRouter se degrada, la aplicación queda limitada por ese proveedor.
- Los endpoints administrativos necesitan una capa de autenticación antes de exponer el servicio a Internet.

## FODA

### Fortalezas

- Arquitectura clara y separada por capas.
- Buen encaje para operación multi-tenant.
- Aislamiento de datos reforzado con RLS.
- Integración LLM desacoplada mediante LiteLLM y OpenRouter.
- API simple de consumir desde canales externos.

### Oportunidades

- Evolucionar a memoria distribuida y sesiones persistentes.
- Agregar autenticación robusta para panel y administración.
- Incorporar métricas, tracing y rate limiting.
- Expandir el portal del tenant para autogestión operativa.
- Añadir colas y procesamiento asíncrono para tareas largas.

### Debilidades

- Memoria conversacional en proceso, no compartida.
- Dependencia alta de disponibilidad externa del LLM.
- Falta visible de control de acceso fuerte en endpoints sensibles.
- Arranque con `create_all()` y scripts manuales en vez de una disciplina completa de migraciones.

### Amenazas

- Picos de latencia o límites del proveedor LLM.
- Fuga de costo si el uso del modelo crece sin observabilidad.
- Exposición de endpoints administrativos si no se blinda la red.
- Pérdida de continuidad conversacional cuando un usuario cambia de worker.

## Posibles mejoras

- Persistir sesiones del agente en Redis o una capa compartida.
- Incorporar autenticación y autorización para `/admin` y `/tenants/me`.
- Mover el esquema de base a migraciones controladas con Alembic.
- Guardar mensajes completos en base para auditoría y analytics.
- Añadir rate limiting por tenant y por canal.
- Implementar retry controlado y circuit breaker para OpenRouter.
- Agregar caché de consultas frecuentes de KB.
- Exponer métricas Prometheus y trazas OpenTelemetry.
- Separar PostgreSQL del VPS de aplicación cuando el tráfico aumente.
- Ajustar sticky sessions en el proxy si se quiere preservar mejor la memoria por worker.
- Incorporar pruebas de carga con escenarios de 30, 60 y 100 usuarios concurrentes.
- Añadir panel de operación para revisar conversaciones, errores y salud por tenant.

## Resumen operativo

Chatbot Core ya tiene una base sólida para operar como backend conversacional multi-tenant en un VPS pequeño o mediano. Para una puesta en producción estable con 30 usuarios concurrentes, la combinación más equilibrada es:

- 4 vCPU
- 8 GB RAM
- 80 GB NVMe
- PostgreSQL 15+
- proxy reverso con TLS
- monitoreo básico

El siguiente salto de madurez está en tres puntos: seguridad de endpoints, sesiones compartidas entre workers y migraciones controladas.
