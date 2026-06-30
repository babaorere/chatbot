# ruff: noqa: E402
from __future__ import annotations

import socket

# Monkey-patch global para obligar al proyecto a usar únicamente IPv4
_original_getaddrinfo = socket.getaddrinfo


def _forced_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == socket.AF_UNSPEC:
        family = socket.AF_INET
    elif family == socket.AF_INET6:
        raise socket.gaierror(socket.EAI_FAMILY, "IPv6 is disabled by application configuration")
    return _original_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _forced_ipv4_getaddrinfo

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from app.lifespan import lifespan
from exceptions import register_exception_handlers
from middleware import RequestIdMiddleware
from controllers import (
    health_router,
    chat_router,
    user_router,
    session_router,
    business_config_router,
    admin_router,
    telegram_router,
    order_router,
    category_router,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Chatbot Core",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
allow_credentials = True
if "*" in origins:
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(user_router)
app.include_router(session_router)
app.include_router(business_config_router)
app.include_router(admin_router)
app.include_router(telegram_router)
app.include_router(order_router)
app.include_router(category_router)
