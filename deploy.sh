#!/bin/bash
# ============================================================================
# Chatbot Core — Deploy Script
# ============================================================================
# Usage: ./deploy.sh [production|staging]
# ============================================================================

set -euo pipefail

ENVIRONMENT="${1:-production}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Pre-flight checks ──────────────────────────────────────────────────────
log "Checking prerequisites..."

command -v docker &>/dev/null || error "Docker not found. Install Docker first."
command -v docker-compose &>/dev/null || command -v docker &>/dev/null || error "Docker Compose not found."

if [[ ! -f "chatbot_core/.env" ]]; then
    error "chatbot_core/.env not found. Copy .env.example and configure it."
fi

if [[ ! -f "nginx.conf" ]]; then
    error "nginx.conf not found."
fi

# ── Pull latest code (if git repo) ─────────────────────────────────────────
if [[ -d ".git" ]]; then
    log "Pulling latest code..."
    git pull --rebase --autostash
fi

# ── Build and deploy ───────────────────────────────────────────────────────
log "Building and deploying..."

if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

$COMPOSE_CMD -f docker-compose.prod.yml down --remove-orphans
$COMPOSE_CMD -f docker-compose.prod.yml build --no-cache
$COMPOSE_CMD -f docker-compose.prod.yml up -d

# ── Wait for health checks ─────────────────────────────────────────────────
log "Waiting for services to be healthy..."
sleep 10

# Check API health
for i in {1..30}; do
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        log "API is healthy!"
        break
    fi
    if [[ $i -eq 30 ]]; then
        error "API failed to become healthy after 300s"
    fi
    log "Waiting for API... ($i/30)"
    sleep 10
done

# ── Post-deploy verification ───────────────────────────────────────────────
log "Running post-deploy checks..."

# Check Nginx
if curl -sf http://localhost/tenant/ > /dev/null 2>&1; then
    log "✅ Tenant Portal: OK"
else
    warn "❌ Tenant Portal: Failed"
fi

if curl -sf http://localhost/admin/ > /dev/null 2>&1; then
    log "✅ Admin Portal: OK"
else
    warn "❌ Admin Portal: Failed"
fi

if curl -sf http://localhost/health > /dev/null 2>&1; then
    log "✅ API Health: OK"
else
    warn "❌ API Health: Failed"
fi

# ── Show status ────────────────────────────────────────────────────────────
echo ""
log "Deployment complete!"
echo ""
$COMPOSE_CMD -f docker-compose.prod.yml ps
echo ""
log "Access points:"
log "  Tenant Portal: http://$(hostname -I | awk '{print $1}')/tenant/"
log "  Admin Portal:  http://$(hostname -I | awk '{print $1}')/admin/"
log "  API:           http://$(hostname -I | awk '{print $1}')/"
log "  Health:        http://$(hostname -I | awk '{print $1}')/health"
echo ""
