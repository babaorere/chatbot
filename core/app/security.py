from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import logging
import time
import uuid

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config.database import get_db
from config.settings import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)
OPTIONAL_BEARER = HTTPBearer(auto_error=False)


async def get_admin_api_key(
    api_key: str | None = Security(API_KEY_HEADER),
) -> str:
    """FastAPI dependency to secure admin endpoints using the X-Admin-API-Key header.

    Checks the incoming header against the configured settings.admin_api_key.
    """
    if not settings.admin_api_key:
        logger.error("ADMIN_API_KEY is not set in settings or .env file.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API Key is not configured on the server.",
        )
    if not api_key or api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials. Invalid or missing Admin API Key.",
        )
    return api_key


security = HTTPBearer()


def _require_jwt_secret() -> bytes:
    if not settings.jwt_secret:
        logger.error("JWT_SECRET no está configurado en settings.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno de configuración de seguridad.",
        )
    return settings.jwt_secret.encode("utf-8")


def _decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _encode_b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_signed_token(token: str, *, expected_type: str | None = None) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Formato de token inválido.",
            )

        header_b64, payload_b64, signature_b64 = parts
        msg = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(_require_jwt_secret(), msg, hashlib.sha256).digest()
        actual_sig = _decode_b64url(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Firma de token inválida.",
            )

        payload = json.loads(_decode_b64url(payload_b64).decode("utf-8"))

        if "exp" in payload and payload["exp"] < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="El token ha expirado.",
            )
        if "nbf" in payload and payload["nbf"] > time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="El token todavía no es válido.",
            )
        if expected_type and payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tipo de token inválido.",
            )

        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error decodificando JWT: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de acceso inválidas o corruptas.",
        )


def create_access_token(
    *,
    subject: str,
    role: str,
    auth_version: int,
    expires_in: timedelta,
    issued_at: datetime | None = None,
) -> str:
    if issued_at is None:
        now = datetime.now(UTC)
    elif issued_at.tzinfo is None:
        now = issued_at.replace(tzinfo=UTC)
    else:
        now = issued_at.astimezone(UTC)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "ver": auth_version,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
    }

    header_b64 = _encode_b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _encode_b64url(json.dumps(payload, separators=(",", ":")).encode())
    msg = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(_require_jwt_secret(), msg, hashlib.sha256).digest()
    signature_b64 = _encode_b64url(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _extract_access_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie_token = request.cookies.get(settings.tenant_access_cookie_name)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


def _validate_admin_key_value(api_key: str | None) -> bool:
    return bool(settings.admin_api_key and api_key == settings.admin_api_key)


def get_current_tenant_user(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Security(OPTIONAL_BEARER),
):
    from models.tenant_auth import TenantPortalUser

    token = _extract_access_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere una sesión válida del panel tenant.",
        )

    payload = decode_signed_token(token, expected_type="access")
    subject = payload.get("sub")
    auth_version = payload.get("ver")
    if not subject or auth_version is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso inválido.",
        )

    user = (
        db.query(TenantPortalUser).filter(TenantPortalUser.id == int(subject)).first()
    )
    if not user or user.disabled_at is not None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ya no es válida.",
        )
    if user.auth_version != int(auth_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión fue reemplazada por un inicio de sesión más reciente.",
        )

    return user


def require_tenant_or_admin_access(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Security(OPTIONAL_BEARER),
):
    admin_key = request.headers.get("X-Admin-API-Key")
    if _validate_admin_key_value(admin_key):
        return {"kind": "admin"}
    user = get_current_tenant_user(request=request, db=db, credentials=credentials)
    return {"kind": "tenant", "user_id": user.id}


def get_current_user_from_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Verifica y decodifica un JWT (HS256) usando la biblioteca estándar."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token de autorización.",
        )
    return decode_signed_token(credentials.credentials)
