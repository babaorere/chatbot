from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


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


def get_current_user_from_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Verifica y decodifica un JWT (HS256) usando la biblioteca estándar."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un token de autorización.",
        )
    token = credentials.credentials
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Formato de token inválido.",
            )

        header_b64, payload_b64, signature_b64 = parts

        # Verificar firma HMAC SHA256
        msg = f"{header_b64}.{payload_b64}".encode("utf-8")
        if not settings.jwt_secret:
            logger.error("JWT_SECRET no está configurado en settings.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno de configuración de seguridad.",
            )
        secret = settings.jwt_secret.encode("utf-8")

        # Decodificación base64url con relleno correcto
        def decode_b64url(s: str) -> bytes:
            padding = "=" * (4 - len(s) % 4)
            return base64.urlsafe_b64decode(s + padding)

        expected_sig = hmac.new(secret, msg, hashlib.sha256).digest()
        actual_sig = decode_b64url(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Firma de token inválida.",
            )

        payload = json.loads(decode_b64url(payload_b64).decode("utf-8"))

        # Verificar expiración
        if "exp" in payload and payload["exp"] < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="El token ha expirado.",
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
