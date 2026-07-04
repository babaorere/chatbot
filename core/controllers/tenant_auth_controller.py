from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.security import get_current_tenant_user
from config.database import get_db
from config.settings import settings
from dtos.request import (
    TenantInviteClaimRequest,
    TenantLoginRequest,
    TenantPasswordChangeRequest,
)
from dtos.response import TenantBootstrapResponse, TenantSessionResponse
from models.tenant_auth import TenantPortalUser
from services.tenant_auth_service import TenantAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenant-auth", tags=["tenant-auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _set_session_cookies(
    response: Response, *, access_token: str, refresh_token: str
) -> None:
    response.set_cookie(
        key=settings.tenant_access_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
        max_age=settings.tenant_access_token_ttl_minutes * 60,
    )
    response.set_cookie(
        key=settings.tenant_refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
        max_age=settings.tenant_refresh_token_ttl_days * 24 * 60 * 60,
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(
        key=settings.tenant_access_cookie_name,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )
    response.delete_cookie(
        key=settings.tenant_refresh_cookie_name,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )


@router.post("/invites/claim", response_model=TenantBootstrapResponse)
def claim_invite(
    data: TenantInviteClaimRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> TenantBootstrapResponse:
    try:
        service = TenantAuthService(db)
        with db.begin():
            user, invite, access_token, refresh_token = service.claim_invite(
                token=data.token,
                full_name=data.full_name,
                password=data.password,
                user_agent=request.headers.get("user-agent"),
                ip_address=_client_ip(request),
            )
        _set_session_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        return TenantBootstrapResponse(
            user=user,
            invite={**invite.__dict__, "invite_url": None},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("tenant_auth.claim_invite failed: %s", exc)
        raise HTTPException(500, "No fue posible activar la cuenta del panel.")


@router.post("/login", response_model=TenantSessionResponse)
def login(
    data: TenantLoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> TenantSessionResponse:
    try:
        service = TenantAuthService(db)
        with db.begin():
            user, access_token, refresh_token = service.authenticate(
                email=data.email,
                password=data.password,
                user_agent=request.headers.get("user-agent"),
                ip_address=_client_ip(request),
            )
        _set_session_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        return TenantSessionResponse(user=user)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("tenant_auth.login failed: %s", exc)
        raise HTTPException(500, "No fue posible iniciar sesión.")


@router.post("/refresh", response_model=TenantSessionResponse)
def refresh(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> TenantSessionResponse:
    refresh_token = request.cookies.get(settings.tenant_refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No hay una sesión renovable.")
    try:
        service = TenantAuthService(db)
        with db.begin():
            user, access_token, new_refresh_token = service.rotate_session(
                refresh_token=refresh_token,
                user_agent=request.headers.get("user-agent"),
                ip_address=_client_ip(request),
            )
        _set_session_cookies(
            response,
            access_token=access_token,
            refresh_token=new_refresh_token,
        )
        return TenantSessionResponse(user=user)
    except ValueError as exc:
        _clear_session_cookies(response)
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("tenant_auth.refresh failed: %s", exc)
        raise HTTPException(500, "No fue posible renovar la sesión.")


@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        service = TenantAuthService(db)
        refresh_token = request.cookies.get(settings.tenant_refresh_cookie_name)
        with db.begin():
            service.revoke_refresh_session(refresh_token)
        _clear_session_cookies(response)
        return {"status": "ok"}
    except Exception as exc:
        logger.error("tenant_auth.logout failed: %s", exc)
        raise HTTPException(500, "No fue posible cerrar la sesión.")


@router.get("/me", response_model=TenantSessionResponse)
def me(
    user: TenantPortalUser = Depends(get_current_tenant_user),
) -> TenantSessionResponse:
    return TenantSessionResponse(user=user)


@router.post("/password/change", response_model=TenantSessionResponse)
def change_password(
    data: TenantPasswordChangeRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    user: TenantPortalUser = Depends(get_current_tenant_user),
) -> TenantSessionResponse:
    try:
        service = TenantAuthService(db)
        with db.begin():
            service.change_password(
                user=user,
                current_password=data.current_password,
                new_password=data.new_password,
            )
            db.refresh(user)
            user, access_token, refresh_token = service.authenticate(
                email=user.email,
                password=data.new_password,
                user_agent=request.headers.get("user-agent"),
                ip_address=_client_ip(request),
            )
        _set_session_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        return TenantSessionResponse(user=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("tenant_auth.change_password failed: %s", exc)
        raise HTTPException(500, "No fue posible actualizar la contraseña.")
