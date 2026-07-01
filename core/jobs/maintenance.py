from __future__ import annotations

import os
import time
from typing import Any


def build_worker_health_payload(queue_name: str | None) -> dict[str, Any]:
    """Construye el payload estándar de salud del worker ARQ."""
    return {
        "status": "ok",
        "worker": "arq",
        "timestamp": int(time.time()),
        "queue_name": queue_name,
        "pid": os.getpid(),
    }


async def job_healthcheck(ctx: dict[str, Any]) -> dict[str, Any]:
    """Minimal durable job used to validate ARQ wiring during phase 1."""
    return build_worker_health_payload(ctx.get("queue_name"))
