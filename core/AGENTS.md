# AGENTS.md — CHATBOT CORE v0.4.0

## MISSION

ROLE: SR-PY/ADK ENG
OBJ : BUILD SINGLE-TENANT MESSAGING SYSTEM FOR NEGOCIO
MODE: STRICT / DETERMINISTIC / ZERO-AMBIGUITY

---

## ABSOLUTE LAWS

LAW-01  FULL TYPE COVERAGE → VAR/PARAM/RETURN
LAW-02  ruff clean + formatted
LAW-03  pytest pass + ≥80% LOGIC
LAW-04  1 FILE = 1 RESPONSIBILITY
LAW-05  Pydantic v2 strict @ ALL BOUNDARIES
LAW-06  FAIL = EXCEPTION (NO STATUS OBJECTS)
LAW-07  NO SIDE-EFFECTS @ TOP LEVEL
LAW-08  EXCEPT = LOG + RAISE → NO silent swallow
LAW-09  ADK TOOLS: Docstrings MUST follow Google/Sphinx extended format for Function Calling
LAW-10  LLM MODEL: LiteLlm + OpenRouter (NO Gemini directo)
LAW-11  SESSION: InMemorySessionService (patrón wmill)
LAW-12  AGENT/RUNNER: Cacheados como singleton por proceso
LAW-13  RAG POLICY: RAG solo para información general; nunca para stock, precios, catálogo, productos o compras

---

## STACK

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
core/
├── main.py                    # FastAPI app + endpoints + lifespan
├── config/
│   ├── __init__.py
│   ├── database.py            # Sync engine (psycopg2) + async engine (asyncpg)
│   └── settings.py            # Pydantic-settings: DATABASE_URL, OPENROUTER_API_KEY, etc.
├── agents/
│   ├── __init__.py
│   ├── constants.py           # GADK_MODEL, GADK_INSTRUCTION, GADK_APP_NAME
│   └── root_agent.py          # ADK Agent + Runner + TOOLS (function calling)
├── models/
│   ├── __init__.py
│   ├── user.py
│   ├── conversation.py
│   ├── message.py
│   └── business_config.py     # Local business configuration profile
├── repositories/
│   ├── __init__.py
│   ├── base.py
│   ├── user_repository.py
│   ├── conversation_repository.py
│   ├── message_repository.py
│   └── business_config_repository.py
├── services/
│   ├── __init__.py
│   ├── agent_factory.py       # Cache management
│   ├── conversation_service.py
│   ├── user_service.py
│   └── business_config_service.py
├── tests/
│   ├── __init__.py
│   └── test_agent_factory.py
├── alembic/
│   └── versions/
├── scripts/
├── Dockerfile
├── pyproject.toml
├── .env
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

# InMemorySessionService (NOT DatabaseSessionService)
runner = Runner(
    agent=agent,
    app_name="chatbot_assistant",
    session_service=InMemorySessionService(),
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

### Docker:

```bash
docker compose -f docker-compose.chatbot.yml up -d --build
```

### Health Check:

```
GET http://localhost:8001/health
→ {"status":"ok","service":"chatbot-core","model":"nemotron-3-super-120b:free","worker_pid":"7"}
```

### Workers:

4 uvicorn workers with uvloop. Each worker has its own LLMService + ADK Runner.

---

## ENVIRONMENT VARIABLES

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for LiteLlm |
| `MODEL_NAME` | No | LiteLlm model identifier |
| `MODEL_DISPLAY` | No | Human-readable model name |
| `APP_ENV` | No | `development` or `production` |
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
