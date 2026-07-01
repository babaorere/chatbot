from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from controllers.health_controller import _read_arq_health


@pytest.mark.asyncio
async def test_read_arq_health_reports_disabled_when_arq_off():
    with patch("controllers.health_controller.settings.arq_enabled", False):
        result = await _read_arq_health()

    assert result["enabled"] is False
    assert result["worker_status"] == "disabled"


@pytest.mark.asyncio
async def test_read_arq_health_reports_ok_with_recent_heartbeat():
    now = int(time.time())
    redis_mock = AsyncMock()
    redis_mock.get.return_value = json.dumps(
        {
            "status": "ok",
            "worker": "arq",
            "timestamp": now,
            "queue_name": "chatbot:jobs",
            "pid": 321,
        }
    )

    with patch("controllers.health_controller.settings.arq_enabled", True), patch(
        "controllers.health_controller.get_redis_client",
        return_value=redis_mock,
    ):
        result = await _read_arq_health()

    assert result["enabled"] is True
    assert result["worker_status"] == "ok"
    assert result["worker_pid"] == 321
    assert result["worker_age_seconds"] >= 0


@pytest.mark.asyncio
async def test_read_arq_health_reports_missing_heartbeat():
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None

    with patch("controllers.health_controller.settings.arq_enabled", True), patch(
        "controllers.health_controller.get_redis_client",
        return_value=redis_mock,
    ):
        result = await _read_arq_health()

    assert result["enabled"] is True
    assert result["worker_status"] == "heartbeat_missing"
