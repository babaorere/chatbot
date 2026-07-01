from __future__ import annotations

import time
from typing import Any


async def job_healthcheck(ctx: dict[str, Any]) -> dict[str, Any]:
    """Minimal durable job used to validate ARQ wiring during phase 1."""
    return {
        "status": "ok",
        "worker": "arq",
        "timestamp": int(time.time()),
        "queue_name": ctx.get("queue_name"),
    }
