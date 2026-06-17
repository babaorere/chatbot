from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_integration = os.getenv("RUN_INTEGRATION_TESTS") == "1"
    if run_integration:
        return

    skip_integration = pytest.mark.skip(
        reason="integration tests require a running API service; set RUN_INTEGRATION_TESTS=1 to enable them"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
