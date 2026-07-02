#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker no está instalado o no está en PATH." >&2
    exit 1
fi

mapfile -t CONTAINER_IDS < <(docker ps -aq)
if ((${#CONTAINER_IDS[@]} > 0)); then
    docker stop "${CONTAINER_IDS[@]}" >/dev/null 2>&1 || true
    docker rm -f "${CONTAINER_IDS[@]}" >/dev/null 2>&1 || true
fi

if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

$COMPOSE_CMD -f docker-compose.yml down --remove-orphans || true
$COMPOSE_CMD -f docker-compose.yml up -d --build
