# Chatbot Core — Production Deployment

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        VPS (Ubuntu 22.04)                   │
│                                                             │
│  ┌──────────────┐         ┌──────────────────────────────┐ │
│  │   Nginx      │────────>│  FastAPI (4 workers)         │ │
│  │   :80        │  /api/* │  :8000 (internal)            │ │
│  │              │         │                              │ │
│  │ /tenant/     │  HTML   │  PostgreSQL (shared)         │ │
│  │ /admin/      │  CSS/JS │  booking-titanium-wm-db-1    │ │
│  │              │         │                              │ │
│  │ + gzip       │         │  OpenRouter API              │ │
│  │ + cache      │         │  nemotron-3-super-120b       │ │
│  │ + HTTP/2     │         └──────────────────────────────┘ │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

## Quick Deploy (VPS)

### 1. Prerequisites

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Git
sudo apt install -y git
```

### 2. Clone & Configure

```bash
git clone <repo-url> /opt/chatbot
cd /opt/chatbot

# Configure environment
cp chatbot_core/.env.example chatbot_core/.env
nano chatbot_core/.env  # Edit with your values
```

### 3. Deploy

```bash
chmod +x deploy.sh
./deploy.sh production
```

### 4. Verify

```bash
# Check services
docker-compose -f docker-compose.prod.yml ps

# Check logs
docker-compose -f docker-compose.prod.yml logs -f

# Test endpoints
curl http://localhost/health
curl http://localhost/tenant/
curl http://localhost/admin/
```

## File Structure

```
chatbot_workspace/
├── docker-compose.prod.yml    # Production compose (Nginx + API)
├── nginx.conf                 # Nginx configuration
├── Dockerfile.nginx           # Nginx Docker image
├── deploy.sh                  # Deploy script
├── rollback.sh                # Rollback script
├── frontend/
│   ├── tenant/                # Tenant Portal (static files)
│   │   ├── index.html
│   │   ├── css/style.css
│   │   └── js/app.js
│   └── admin/                 # Admin Portal (static files)
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
└── chatbot_core/
    ├── Dockerfile             # FastAPI Docker image
    ├── .env                   # Environment variables
    └── ...                    # Backend code
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key |
| `MODEL_NAME` | No | Default LLM model |
| `APP_ENV` | No | `production` or `development` |
| `LOG_LEVEL` | No | `INFO`, `WARNING`, `ERROR` |

## SSL/HTTPS (Let's Encrypt)

### Automated Setup (Recommended)

```bash
# One-command SSL setup
sudo ./setup-ssl.sh chatbot.tu-dominio.com admin@tu-dominio.com
```

This script will:
1. Install Certbot if needed
2. Request SSL certificate
3. Update Nginx config with SSL settings
4. Enable HTTP → HTTPS redirect
5. Configure auto-renewal (daily at 3 AM)

### Manual Setup

```bash
# Stop Nginx container
docker compose -f docker-compose.prod.yml stop nginx

# Get certificate
sudo certbot certonly --standalone -d chatbot.tu-dominio.com -m admin@tu-dominio.com

# Update nginx.conf (uncomment SSL lines)
# Then restart
docker compose -f docker-compose.prod.yml up -d nginx
```

### Auto-Renewal

Certificates auto-renew via cron job. Verify with:

```bash
sudo certbot renew --dry-run
```

## Rate Limiting

The API has built-in rate limiting to prevent abuse:

| Endpoint | Limit | Burst | Purpose |
|----------|-------|-------|---------|
| `/chat` | 10 req/min | 5 | Prevent OpenRouter abuse |
| `/chat/stream` | No limit | — | SSE streaming |
| `/admin/*` | 5 req/min | 3 | Prevent brute force |
| `/*` (general) | 30 req/min | 10 | General API protection |
| `/health` | No limit | — | Monitoring |

Rate-limited requests return `429 Too Many Requests`:

```json
{"error": "Too many requests. Please try again later."}
```

### Adjusting Limits

Edit `nginx.conf` rate zones:

```nginx
# Increase chat limit to 20/min
limit_req_zone $binary_remote_addr zone=chat_limit:10m rate=20r/m;
```

## Monitoring

```bash
# Check resource usage
docker stats

# Check Nginx access logs
docker-compose -f docker-compose.prod.yml logs nginx

# Check API logs
docker-compose -f docker-compose.prod.yml logs api
```

## Backup

```bash
# Backup database
pg_dump -h booking-titanium-wm-db-1 -U windmill chatbot > backup_$(date +%Y%m%d).sql

# Backup frontend
tar -czf frontend_backup_$(date +%Y%m%d).tar.gz frontend/

# Backup environment
cp chatbot_core/.env .env.backup_$(date +%Y%m%d)
```

## Troubleshooting

### API not starting
```bash
docker-compose -f docker-compose.prod.yml logs api
```

### Nginx 502 Bad Gateway
```bash
# Check if API is running
docker-compose -f docker-compose.prod.yml ps api

# Check Nginx config
docker-compose -f docker-compose.prod.yml exec nginx nginx -t
```

### Database connection failed
```bash
# Test connection
docker-compose -f docker-compose.prod.yml exec api python -c "
from config.database import _sync_engine
conn = _sync_engine.connect()
print('Connected!')
conn.close()
"
```

## Windmill Integration (Phase 6)

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Windmill Stack                               │
│                                                                     │
│  Telegram Webhook                                                   │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐ │
│  │ chatbot_flow  │───>│chatbot_webhook│───>│ chatbot_   │ │
│  │ (orchestrator)   │    │ (parse + route)  │    │    chat       │ │
│  │                  │<───┘                  │    │ (HTTP /chat)  │ │
│  │                  │    └──────────────────┘    └───────┬───────┘ │
│  └───────┬────────┘                                      │         │
│          │                                               │         │
│          ▼                                               │         │
│  ┌──────────────────┐                                    │         │
│  │  telegram_send   │                                    │         │
│  │  (send response) │                                    │         │
│  └──────────────────┘                                    │         │
│                                                          │         │
└──────────────────────────────────────────────────────────┼─────────┘
                                                           │
                                                           ▼
                                              ┌────────────────────────┐
                                              │  chatbot_core_api   │
                                              │  :8000                 │
                                              │                        │
                                              │  - Tenant resolution   │
                                              │  - RAG (FTS + pgvector)│
                                              │  - LLM (OpenRouter)    │
                                              │  - Session management  │
                                              └────────────────────────┘
```

### Windmill Scripts

| Script | Path | Purpose |
|--------|------|---------|
| **chatbot_chat** | `f/chatbot_chat/main.py` | Generic chat client for chatbot API. Accepts user_id, message, platform, channel_identifier, tenant_id, session_id. |
| **chatbot_webhook** | `f/chatbot_webhook/main.py` | Telegram webhook receiver. Parses Telegram payload, extracts bot_token for tenant resolution, calls chatbot API. |
| **chatbot_flow** | `f/chatbot_flow/main.py` | Workflow orchestrator. Chains webhook → chat → telegram_send. |
| **chatbot_health_check** | `f/chatbot_health_check/main.py` | Health check + API endpoint verification. |

### Configuration

#### Windmill Variable

Create a Windmill variable at `u/admin/CHATBOT_API_URL`:
```
http://chatbot_core_api:8000
```

If not set, scripts default to the internal Docker network URL above.

#### Docker Volume Mount

The chatbot_core package is mounted as read-only on all Windmill workers:
```yaml
# docker-compose.windmill.yml
services:
  windmill_worker:
    volumes:
      - ../chatbot_workspace/chatbot_core:/opt/chatbot_core:ro
```

### Tenant Resolution

The chatbot API resolves tenants via two strategies:

1. **Direct Tenant ID**: Pass `X-Tenant-ID` header with tenant UUID
2. **Channel Mapping**: Pass `X-Platform` + `X-Channel-Identifier` headers (e.g., `telegram` + bot token)

The `chatbot_webhook` script automatically uses strategy 2 with:
- `X-Platform: telegram`
- `X-Channel-Identifier: <bot_token>`

### Usage Examples

#### Direct Chat (chatbot_chat)

```python
# Windmill script inputs
result = chatbot_chat(
    user_id="12345",
    message="Qué cervezas tienen?",
    platform="telegram",
    channel_identifier="bot-token-123:ABC",
    # Optional: session_id="existing-session"
)

# Returns:
# {
#   "response": "Tenemos cerveza artesanal...",
#   "session_id": "sess-new",
#   "user_id": "12345",
#   "tenant_slug": "el_buen_trago"
# }
```

#### Full Flow (chatbot_flow)

```python
# Triggered by Telegram webhook
result = chatbot_flow(
    update_id=123456,
    message_chat_id=789,
    message_text="Hola, qué ofrecen?",
    message_from_id=789,
    bot_token="bot-token-123:ABC",
)
```

### Error Handling

All scripts follow the fail-fast pattern:
- HTTP errors → `RuntimeError` with status code and response body
- Timeouts → `RuntimeError` with timeout message
- Invalid input → `RuntimeError` with validation details

Errors propagate to Windmill as failed jobs (not silent failures).
