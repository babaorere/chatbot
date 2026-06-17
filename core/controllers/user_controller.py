from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config.database import get_db, set_tenant_context
from models.tenant import Tenant
from services import TenantService, UserService
from dtos.request import UserCreateRequest
from dtos.response import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


def resolve_tenant(request: Request, db: Session) -> Tenant:
    tenant_id_header = request.headers.get("X-Tenant-ID")
    if not tenant_id_header:
        logger.warning("Missing X-Tenant-ID header on request: %s", request.url.path)
        raise HTTPException(401, "Missing X-Tenant-ID header")

    try:
        tenant_id = uuid.UUID(tenant_id_header)
    except ValueError as e:
        logger.warning(
            "Invalid X-Tenant-ID header format: %s — %s", tenant_id_header, e
        )
        raise HTTPException(401, "Invalid X-Tenant-ID format") from e

    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    if not tenant:
        logger.warning("Tenant not found or inactive: %s", tenant_id)
        raise HTTPException(403, f"Tenant {tenant_id} not found or inactive")

    return tenant


@router.post("", response_model=UserResponse)
def create_user(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> UserResponse:
    try:
        if not fastapi_request:
            logger.warning("create_user called without request context")
            raise HTTPException(401, "Missing X-Tenant-ID header")

        tenant = resolve_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))
        user_svc = UserService(db, tenant.id)
        user = user_svc.get_or_create(
            external_id=data.external_id,
            platform=data.platform,
            display_name=data.display_name,
        )
        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error("create_user failed [request_id=%s]: %s", request_id, e)
        raise


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> UserResponse:
    try:
        if not fastapi_request:
            logger.warning("get_user called without request context")
            raise HTTPException(401, "Missing X-Tenant-ID header")

        tenant = resolve_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))
        user_svc = UserService(db, tenant.id)
        user = user_svc.get_by_id(user_id)
        if not user:
            logger.warning(
                "User not found: user_id=%s, tenant_id=%s", user_id, tenant.id
            )
            raise HTTPException(404, "User not found")
        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error(
            "get_user failed [request_id=%s, user_id=%s]: %s", request_id, user_id, e
        )
        raise


@router.get("", response_model=list[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[UserResponse]:
    try:
        if not fastapi_request:
            logger.warning("list_users called without request context")
            raise HTTPException(401, "Missing X-Tenant-ID header")

        tenant = resolve_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))
        user_svc = UserService(db, tenant.id)
        users = user_svc.list_users(skip=skip, limit=limit)
        return [UserResponse.model_validate(u) for u in users]
    except HTTPException:
        raise
    except Exception as e:
        request_id = (
            getattr(fastapi_request.state, "request_id", "unknown")
            if fastapi_request
            else "unknown"
        )
        logger.error("list_users failed [request_id=%s]: %s", request_id, e)
        raise
