#!/usr/bin/env bash
# Iniciar chatbot en producción
docker compose -f docker-compose.prod.yml up -d --build
