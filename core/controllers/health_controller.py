from __future__ import annotations

import os

from fastapi import APIRouter
from config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "botilleria-core",
        "version": "1.0.0",
        "multi_tenant": "true",
        "session_backend": settings.session_backend,
        "worker_pid": str(os.getpid()),
    }
