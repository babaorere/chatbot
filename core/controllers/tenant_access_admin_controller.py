from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.security import get_admin_api_key
from config.database import get_db
from config.value_limits import PAGINATION_LIMIT_MAX, PAGINATION_LIMIT_MIN
from dtos.request import TenantInviteCreateRequest, TenantUserDisableRequest
from dtos.response import TenantInviteResponse, TenantPortalUserResponse
from services.tenant_auth_service import TenantAuthService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/tenant-access",
    tags=["tenant-access-admin"],
    dependencies=[Depends(get_admin_api_key)],
)


@router.get("/users", response_model=list[TenantPortalUserResponse])
def list_tenant_users(
    limit: int = Query(default=100, ge=PAGINATION_LIMIT_MIN, le=PAGINATION_LIMIT_MAX),
    db: Session = Depends(get_db),
) -> list[TenantPortalUserResponse]:
    try:
        service = TenantAuthService(db)
        users = service.list_users(limit=limit)
        return [TenantPortalUserResponse.model_validate(user) for user in users]
    except Exception as exc:
        logger.error("tenant_access_admin.list_tenant_users failed: %s", exc)
        raise HTTPException(500, "No fue posible listar usuarios tenant.")


@router.get("/invites", response_model=list[TenantInviteResponse])
def list_tenant_invites(
    limit: int = Query(default=50, ge=PAGINATION_LIMIT_MIN, le=PAGINATION_LIMIT_MAX),
    db: Session = Depends(get_db),
) -> list[TenantInviteResponse]:
    try:
        service = TenantAuthService(db)
        invites = service.list_invites(limit=limit)
        return [TenantInviteResponse.model_validate(invite) for invite in invites]
    except Exception as exc:
        logger.error("tenant_access_admin.list_tenant_invites failed: %s", exc)
        raise HTTPException(500, "No fue posible listar invitaciones.")


@router.post("/invites", response_model=TenantInviteResponse, status_code=201)
def create_tenant_invite(
    data: TenantInviteCreateRequest,
    db: Session = Depends(get_db),
) -> TenantInviteResponse:
    try:
        service = TenantAuthService(db)
        with db.begin():
            invite, raw_token = service.create_invite(
                email=data.email,
                full_name=data.full_name,
                role=data.role,
                created_by_admin_id=data.created_by_admin_id,
            )
        return TenantInviteResponse.model_validate(
            {**invite.__dict__, "invite_url": service.build_invite_url(raw_token)}
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("tenant_access_admin.create_tenant_invite failed: %s", exc)
        raise HTTPException(500, "No fue posible crear la invitación.")


@router.post("/invites/{invite_id}/revoke", response_model=TenantInviteResponse)
def revoke_tenant_invite(
    invite_id: str,
    db: Session = Depends(get_db),
) -> TenantInviteResponse:
    try:
        service = TenantAuthService(db)
        with db.begin():
            invite = service.revoke_invite(invite_id)
        return TenantInviteResponse.model_validate(invite)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("tenant_access_admin.revoke_tenant_invite failed: %s", exc)
        raise HTTPException(500, "No fue posible revocar la invitación.")


@router.post("/users/{user_id}/disable", response_model=TenantPortalUserResponse)
def disable_tenant_user(
    user_id: int,
    data: TenantUserDisableRequest,
    db: Session = Depends(get_db),
) -> TenantPortalUserResponse:
    try:
        service = TenantAuthService(db)
        with db.begin():
            user = service.disable_user(user_id, disabled=data.disabled)
        return TenantPortalUserResponse.model_validate(user)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("tenant_access_admin.disable_tenant_user failed: %s", exc)
        raise HTTPException(500, "No fue posible actualizar el usuario tenant.")
