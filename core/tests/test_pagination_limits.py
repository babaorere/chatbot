from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.security import get_admin_api_key, get_current_tenant_user
from config.database import get_db
from config.value_limits import PAGINATION_LIMIT_MAX, PAGINATION_SKIP_MAX
from main import app


@pytest.fixture
def api_overrides():
    app.dependency_overrides[get_admin_api_key] = lambda: "test-admin-key"
    app.dependency_overrides[get_current_tenant_user] = lambda: {"sub": "tenant-user"}
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_admin_api_key, None)
        app.dependency_overrides.pop(get_current_tenant_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/business/config/products", {"limit": PAGINATION_LIMIT_MAX + 1}),
        ("/business/config/products", {"skip": -1}),
        ("/business/config/products", {"skip": PAGINATION_SKIP_MAX + 1}),
        ("/business/config/kb", {"limit": 0}),
        ("/users", {"limit": PAGINATION_LIMIT_MAX + 1}),
        ("/admin/tenant-access/users", {"limit": PAGINATION_LIMIT_MAX + 1}),
        ("/admin/tenant-access/invites", {"limit": 0}),
        ("/business/me/products", {"skip": PAGINATION_SKIP_MAX + 1}),
    ],
)
@pytest.mark.asyncio
async def test_paginated_endpoints_reject_out_of_range_query_values(
    api_overrides,
    path: str,
    query: dict[str, int],
) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(path, params=query)

    assert response.status_code == 422
