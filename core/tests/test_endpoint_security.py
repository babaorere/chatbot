from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.security import get_admin_api_key
from controllers.business_config_controller import router as business_config_router
from controllers.category_controller import router as category_router
from controllers.session_controller import router as session_router


def _get_route(path: str, method: str):
    for route in (
        list(business_config_router.routes)
        + list(session_router.routes)
        + list(category_router.routes)
    ):
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            return route
    raise AssertionError(f"Route not found: {method} {path}")


def _dependency_names(route) -> set[str]:
    return {dep.call.__name__ for dep in route.dependant.dependencies if dep.call}


def test_business_config_profile_route_includes_admin_dependency():
    route = _get_route("/business/config/profile", "GET")

    dependency_names = _dependency_names(route)

    assert "get_admin_api_key" in dependency_names


def test_session_history_route_includes_admin_dependency():
    route = _get_route("/sessions/{session_id}/history", "GET")

    dependency_names = _dependency_names(route)

    assert "get_admin_api_key" in dependency_names


def test_create_category_route_includes_admin_dependency():
    route = _get_route("/categories", "POST")

    dependency_names = _dependency_names(route)

    assert "get_admin_api_key" in dependency_names


@pytest.mark.asyncio
async def test_get_admin_api_key_rejects_missing_header():
    from unittest.mock import patch

    with patch("app.security.settings.admin_api_key", "test-admin-key"):
        with pytest.raises(HTTPException) as exc_info:
            await get_admin_api_key(api_key=None)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_admin_api_key_accepts_valid_header():
    from unittest.mock import patch

    with patch("app.security.settings.admin_api_key", "test-admin-key"):
        api_key = await get_admin_api_key(api_key="test-admin-key")

    assert api_key == "test-admin-key"


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_missing_token_raises_401():
    from app.security import get_current_user_from_jwt

    with pytest.raises(HTTPException) as exc_info:
        get_current_user_from_jwt(credentials=None)

    assert exc_info.value.status_code == 401
    assert "Se requiere un token de autorización" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_invalid_signature_raises_401():
    import base64
    import json
    from fastapi.security import HTTPAuthorizationCredentials
    from app.security import get_current_user_from_jwt
    from unittest.mock import patch

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "123", "exp": 9999999999}

    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode())
        .decode()
        .rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode())
        .decode()
        .rstrip("=")
    )
    # Token with arbitrary/invalid signature
    token = f"{header_b64}.{payload_b64}.invalidsignaturehere"
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with patch("app.security.settings.jwt_secret", "test-secret-key"):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_from_jwt(credentials=credentials)

    assert exc_info.value.status_code == 401
    assert "Firma de token inválida" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_expired_token_raises_401():
    import base64
    import json
    import hmac
    import hashlib
    import time
    from fastapi.security import HTTPAuthorizationCredentials
    from app.security import get_current_user_from_jwt
    from unittest.mock import patch

    secret = "test-secret-key"
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "123", "exp": int(time.time()) - 10}  # Expired 10s ago

    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode())
        .decode()
        .rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode())
        .decode()
        .rstrip("=")
    )
    msg = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")

    token = f"{header_b64}.{payload_b64}.{sig_b64}"
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with patch("app.security.settings.jwt_secret", secret):
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_from_jwt(credentials=credentials)

    assert exc_info.value.status_code == 401
    assert "El token ha expirado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_valid_token_returns_payload():
    import base64
    import json
    import hmac
    import hashlib
    import time
    from fastapi.security import HTTPAuthorizationCredentials
    from app.security import get_current_user_from_jwt
    from unittest.mock import patch

    secret = "test-secret-key"
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": "123", "exp": int(time.time()) + 3600}

    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode())
        .decode()
        .rstrip("=")
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode())
        .decode()
        .rstrip("=")
    )
    msg = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")

    token = f"{header_b64}.{payload_b64}.{sig_b64}"
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with patch("app.security.settings.jwt_secret", secret):
        res = get_current_user_from_jwt(credentials=credentials)

    assert res["sub"] == "123"
