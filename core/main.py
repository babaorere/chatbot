from __future__ import annotations

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
    tenant_router,
    user_router,
    session_router,
    tenant_portal_router,
    admin_router,
    telegram_router,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Botilleria Core (Multi-Tenant)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(tenant_router)
app.include_router(user_router)
app.include_router(session_router)
app.include_router(tenant_portal_router)
app.include_router(admin_router)
app.include_router(telegram_router)
