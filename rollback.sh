#!/bin/bash
# ============================================================================
# Chatbot Core — Rollback Script
# ============================================================================
# Usage: ./rollback.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

echo "Rolling back to previous deployment..."
$COMPOSE_CMD -f docker-compose.prod.yml down
$COMPOSE_CMD -f docker-compose.prod.yml up -d

echo "Rollback complete."
$COMPOSE_CMD -f docker-compose.prod.yml ps
