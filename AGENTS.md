# ============================================================================
# CHATBOT CORE — RULES & STANDARDS
# ============================================================================

PYTHON: 3.13 (MANDATORY EXCLUSIVITY)
PKG   : pip (Docker) / uv (local dev)
LINT  : ruff
TEST  : pytest
DATA  : pydantic v2
LLM   : google-adk[extensions]>=2.0.0 + litellm>=1.71.2
API   : OpenRouter (NO Google API key directa)

---

## RAG POLICY

RAG solo está permitido para información general del negocio:
- Horarios de atención.
- Zonas de atención y delivery.
- Formas de pago.
- Servicios generales.
- Información institucional no dinámica.

RAG está prohibido para productos, stock, precios, catálogo, compras o cotizaciones. Esos casos deben resolverse con `consultar_stock`, `consultar_precio` u otras herramientas reales, nunca con contexto RAG.

---

## PROJECT STRUCTURE

```
chatbot/
├── core/                          # Aplicación principal (FastAPI)
│   ├── main.py                    # FastAPI app entry point
│   ├── app/
│   │   ├── container.py           # Dependency injection container
│   │   └── lifespan.py            # Startup/shutdown (DB, Redis, ADK)
│   ├── agents/
│   │   ├── constants.py           # MODEL, INSTRUCTION, APP_NAME
│   │   └── root_agent.py          # ADK Agent + Runner + tools
│   ├── application/               # Capa de aplicación (DDD)
│   │   ├── ports/                 # Interfaces: channel_port, llm_port, rag_port
│   │   └── use_cases/
│   │       ├── commands.py
│   │       └── process_message.py # Orquesta mensaje → LLM → respuesta
│   ├── config/
│   │   ├── database.py            # Sync (psycopg2) + Async (asyncpg) engines
│   │   ├── redis.py               # Redis client factory (Upstash TLS)
│   │   └── settings.py            # Pydantic-settings: todas las variables de entorno
│   ├── controllers/               # FastAPI routers
│   │   ├── admin_controller.py
│   │   ├── business_config_controller.py
│   │   ├── category_controller.py
│   │   ├── chat_controller.py
│   │   ├── health_controller.py
│   │   ├── order_controller.py
│   │   ├── session_controller.py
│   │   ├── telegram_controller.py # Webhook Telegram
│   │   └── user_controller.py
│   ├── domain/                    # Entidades y lógica de dominio
│   ├── dtos/
│   │   ├── request/               # ChatRequest, ConfigRequest, UserRequest
│   │   └── response/              # ChatResponse, ConfigResponse, etc.
│   ├── exceptions/
│   │   ├── global_handler.py      # FastAPI exception handlers
│   │   └── *_exceptions.py        # Por dominio: user, conversation, config
│   ├── infrastructure/
│   │   ├── channels/
│   │   │   └── telegram_fsm.py    # FSM del flujo Telegram
│   │   ├── llm/
│   │   │   └── adk_provider.py    # ADKLLMProvider (implementa llm_port)
│   │   └── rag/
│   │       └── kb_rag_provider.py # RAG sobre knowledge base
│   ├── middleware/
│   │   └── request_id.py
│   ├── models/                    # SQLAlchemy ORM
│   │   ├── business_config.py
│   │   ├── cart.py
│   │   ├── category.py
│   │   ├── conversation.py
│   │   ├── knowledge_base.py
│   │   ├── message.py
│   │   ├── order.py
│   │   ├── product.py
│   │   ├── system_setting.py
│   │   └── user.py
│   ├── repositories/              # Data access layer
│   │   ├── conversation_repository.py
│   │   ├── kb_repository.py
│   │   ├── message_repository.py
│   │   ├── product_repository.py
│   │   ├── system_setting_repository.py
│   │   └── user_repository.py
│   ├── services/
│   │   ├── agent_factory.py
│   │   ├── cart_service.py
│   │   ├── category_service.py
│   │   ├── embedding_service.py
│   │   ├── kb_service.py
│   │   ├── order_service.py
│   │   ├── product_service.py
│   │   ├── rag_context_builder.py
│   │   ├── rag_policy.py
│   │   ├── redis_session_service.py  # RedisSessionService (Upstash)
│   │   ├── session_service_factory.py
│   │   ├── telegram_service.py
│   │   ├── transactional.py
│   │   └── user_service.py
│   ├── scripts/
│   │   └── seed_db.py
│   ├── tests/                     # pytest — cobertura por módulo
│   ├── Dockerfile
│   └── pyproject.toml
├── docker-compose.yml             # Solo desarrollo local
├── docker-compose.prod.yml        # Producción (db + api + nginx + tunnel)
├── docker-compose.monitoring.yml  # Observabilidad (opcional)
├── nginx.conf                     # Reverse proxy + rate limiting
├── .env                           # Variables de entorno (no commitear)
└── .env.example
```

---

## ADK TOOL DOCSTRING STANDARD (LAW-09)

Every tool function exposed to the ADK agent MUST have a docstring that follows this exact format.
Google ADK parses these docstrings to generate JSON schemas for function calling.

### Template:

```python
def tool_name(param: str | None = None) -> str:
    """[Descripción clara y unívoca de la función].

    [Instrucciones operativas para el modelo. Cuándo invocarla y cuándo NO].

    Args:
        param (str | None): [Descripción detallada de qué es y formato esperado].

    Returns:
        str: [Descripción de la respuesta que recibirá el contexto del modelo].
    """
```

### Rules:

1. **First line**: Action verb + what the function does. No vague language.
2. **Second paragraph**: When to invoke + when NOT to invoke. Prevents infinite loops.
3. **Args section**: Every parameter with type + purpose + format + None behavior.
4. **Returns section**: Exact format the model receives after ADK executes the tool.

### Example (from `consultar_stock`):

```python
def consultar_stock(producto: str | None = None) -> str:
    """Inicia una consulta de disponibilidad de un producto específico en el
    inventario de la negocio.

    Invoca esta herramienta cuando el usuario pregunte si un producto está
    disponible, si tienen cierto licor/cerveza/vino en stock, o cuando
    exprese intención de comprar algo y necesites confirmar existencia
    (ej: 'tienen pisco sour?', 'hay cerveza artesanal de trigo?').
    NO la invoques para preguntas sobre precios (usa consultar_precio),
    horarios (usa get_chatbot_info), o saludos generales.

    Args:
        producto: Nombre del producto que el usuario busca, en formato
            texto libre (ej: 'pisco', 'vino tinto', 'cerveza artesanal').
            Usa None si el usuario no mencionó un producto específico.

    Returns:
        str: Mensaje de confirmación indicando que se consultará la
            disponibilidad del producto solicitado. Si producto fue
            proporcionado, incluye el nombre en la respuesta.
    """
```

---

## ADK AGENT PATTERN (LAW-10, LAW-11, LAW-12)

### Model Configuration:

```python
from google.adk import Agent, Runner
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService

# LiteLlm + OpenRouter (NOT direct Gemini)
agent = Agent(
    name="chatbot_assistant",
    model=LiteLlm(model="openrouter/nvidia/nemotron-3-super-120b-a12b:free", api_key=openrouter_key),
    instruction="Eres el asistente virtual de la Negocio El Buen Trago...",
    tools=[get_current_datetime, get_chatbot_info, consultar_stock, consultar_precio, contactar_humano],
)

# Session backend: Redis (Upstash TLS) en producción via RedisSessionService
# InMemorySessionService solo en tests/desarrollo local sin Redis
runner = Runner(
    agent=agent,
    app_name="chatbot_assistant",
    session_service=InMemorySessionService(),  # reemplazar por RedisSessionService en prod
    auto_create_session=True,
)
```

### Session Isolation:

Each `(user_id, session_id)` pair gets its own isolated conversation context.
Users run in parallel without contention. Same user: sequential within session.

---

## ENTRYPOINT PATTERN

### FastAPI Sync Wrapper:

```python
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db), llm: LLMService = Depends(get_llm_service)) -> ChatResponse:
    user = user_svc.get_or_create(external_id=request.user_id, platform=request.platform)
    session_id = request.session_id or str(uuid.uuid4())
    response_text = await llm.run_chat(user_id=request.user_id, session_id=session_id, message=request.message)
    return ChatResponse(session_id=session_id, user_id=request.user_id, response=response_text)
```

### Streaming SSE:

```python
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, db: Session = Depends(get_db), llm: LLMService = Depends(get_llm_service)) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        async for chunk in llm.run_chat_stream(...):
            yield {"event": "chunk", "data": chunk}
        yield {"event": "done", "data": session_id}
    return EventSourceResponse(event_generator())
```

---

## ERROR MODEL

SUCCESS → VALUE
FAIL    → raise Exception

FORBIDDEN:
- silent except
- return error dict
- except: pass

---

## TEST CONTRACT

AAA PATTERN ONLY

RULES:
- 1 TEST = 1 BEHAVIOR
- FILE MIRROR STRUCTURE
- NO NETWORK/DB (mock LLM calls)

NAME:
test_<unit>_<case>_<expected>

---

## WINDMILL INTEGRATION

chatbot_core is mounted as read-only volume in Windmill workers:
- Path: `/opt/chatbot_core`
- Usage: `sys.path.insert(0, '/opt/chatbot_core')`
- Windmill scripts call the FastAPI API via HTTP: `http://chatbot_core_api:8000/chat`

---

## DEPLOYMENT

### Compose file (producción):

```bash
# Levantar stack completo (db → api → nginx → tunnel)
docker compose -f docker-compose.prod.yml up -d --remove-orphans

# Bajar stack limpio
docker compose -f docker-compose.prod.yml down --remove-orphans

# Rebuild API tras cambios de código
docker compose -f docker-compose.prod.yml up -d --build api
```

> `docker-compose.yml` es solo para desarrollo local. NUNCA usar en prod.

### Startup order y tiempos:

```
db      → healthy  ~11s
api     → healthy  ~45-60s  (start_period en healthcheck)
nginx   → started  inmediato tras api healthy
tunnel  → started  inmediato tras nginx
```

### Health Check:

```bash
# Local
curl http://localhost/health
# → {"status":"ok","service":"chatbot-core","model":"deepseek-v4-flash","session_backend":"redis"}

# Via tunnel (end-to-end)
curl https://bot.stax.ink/health
```

### Workers:

Uvicorn con WatchFiles en dev / uvloop en prod. Cada worker tiene su propio LLMService + ADK Runner.

---

## INFRASTRUCTURE

### Redis — Upstash (externo TLS)

- **Backend exclusivo de sesiones**: Upstash Redis Cloud (TLS, `rediss://`)
- **NO hay Redis interno** en el stack de producción
- URL configurada en `.env` como `REDIS_URL=rediss://...@master-grackle-154605.upstash.io:6379`
- El `docker-compose.prod.yml` **no tiene** servicio `redis` — todo va a Upstash
- Verificar conexión: `redis.ping()` → `True`

### Cloudflare Tunnel

- Servicio: `cloudflare_tunnel` en `docker-compose.prod.yml`
- Rutea `bot.stax.ink` → `http://bot:7080` (configurado en dashboard Cloudflare)
- El hostname `bot` es un **alias de red Docker** del contenedor `chatbot_nginx`
- **CRÍTICO**: sin el alias `bot` en la red de nginx, el tunnel da `no such host` y el webhook falla con 530/502

### Nginx — alias `bot` (OBLIGATORIO)

El servicio nginx en `docker-compose.prod.yml` DEBE tener:

```yaml
networks:
  chatbot_net:
    aliases:
      - bot
```

Sin este alias el tunnel de Cloudflare no puede resolver el origen y todos los requests fallan.

### Nginx — resolver Docker DNS (OBLIGATORIO)

El `nginx.conf` DEBE tener el resolver de Docker para evitar fallo al arrancar si `api` no está aún en DNS:

```nginx
resolver 127.0.0.11 valid=10s ipv6=off;

server {
    set $api_backend http://api:8000;
    # ...
    location / {
        proxy_pass $api_backend;  # variable, NO upstream estático
    }
}
```

Sin esto, nginx crashea al inicio con `host not found in upstream "api:8000"`.

### Puertos del host

| Puerto | Servicio | Notas |
|---|---|---|
| `80` | nginx → API | Apache del sistema debe estar desinstalado |
| `443` | nginx → API (SSL) | Certificados via Let's Encrypt |
| `7080` | nginx interno | Usado por el tunnel (`bot:7080`) |
| `5433` | PostgreSQL | Solo localhost, no expuesto externamente |

> Apache (`apache2`) conflicta con el puerto 80. Debe estar desinstalado: `sudo apt remove apache2`

### Telegram Webhook

- URL: `https://bot.stax.ink/telegram/webhook/<BOT_TOKEN>`
- Verificar estado: `GET https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- Estado correcto: `pending_update_count: 0`, `last_error_message: null`
- Error 530 = tunnel caído o sin alias `bot`
- Error 502 = nginx caído o no resuelve `api`

### Diagnóstico rápido

```bash
# 1. Contenedores
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Conexiones internas
docker exec chatbot_api python3 -c "from config.database import SessionLocal; import sqlalchemy; db=SessionLocal(); print(db.execute(sqlalchemy.text('SELECT 1')).fetchone())"

# 3. Redis
docker exec chatbot_api python3 -c "import asyncio,redis.asyncio as r,os; asyncio.run(r.from_url(os.environ['REDIS_URL']).ping()) and print('OK')"

# 4. End-to-end
curl https://bot.stax.ink/health

# 5. Webhook
TOKEN=$(grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2)
curl -s https://api.telegram.org/bot$TOKEN/getWebhookInfo | python3 -m json.tool
```

---

## ENVIRONMENT VARIABLES

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string (`postgresql://user:pass@db:5432/chatbot`) |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key para LiteLlm |
| `REDIS_URL` | Yes | Upstash TLS URL (`rediss://default:...@host:6379`) |
| `SESSION_BACKEND` | Yes | Siempre `redis` en producción |
| `REDIS_NAMESPACE` | No | Prefijo de claves Redis (default: `chatbot:adk:v1`) |
| `REDIS_UPSTASH_REST_URL` | No | REST API URL de Upstash (opcional, para admin) |
| `REDIS_UPSTASH_REST_TOKEN` | No | Token REST de Upstash |
| `TELEGRAM_BOT_TOKEN` | Yes | Token del bot de Telegram (`123456:ABC...`) |
| `TELEGRAM_ID` | Yes | Chat ID del admin/owner |
| `CLOUDFLARE_TUNNEL_TOKEN` | Yes | Token del tunnel de Cloudflare |
| `MODEL_NAME` | No | Identificador LiteLlm (default: `deepseek-v4-flash`) |
| `MODEL_DISPLAY` | No | Nombre legible del modelo |
| `APP_ENV` | No | `development` o `production` |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## DELIVERY GATES

ruff check .
ruff format .
pytest -q

ALL MUST PASS

---

## EXECUTION ORDER

1 SPEC
2 MODEL
3 LOGIC
4 ENTRY
5 TEST
6 GATES
7 COMMIT

STOP IF FAIL

---

## FINAL DIRECTIVE

DISCIPLINE > SPEED
STRICTNESS > FLEXIBILITY
DETERMINISM > MAGIC

EXECUTE. NO DEVIATION.
