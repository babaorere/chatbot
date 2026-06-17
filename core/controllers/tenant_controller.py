from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from services import TenantService
from dtos.request import TenantCreateRequest, ChannelRouteCreateRequest
from dtos.response import TenantResponse, ChannelRouteResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse)
def create_tenant(
    data: TenantCreateRequest,
    db: Session = Depends(get_db),
) -> TenantResponse:
    try:
        tenant_service = TenantService(db)
        with db.begin():
            tenant = tenant_service.create_tenant(
                slug=data.slug,
                name=data.name,
                config={
                    "instruction": data.instruction,
                    "model": data.model,
                    "api_key": data.api_key,
                    "products": [],
                },
            )
        return TenantResponse.model_validate(tenant)
    except Exception as e:
        logger.error("create_tenant failed [slug=%s]: %s", data.slug, e)
        raise


@router.post("/{tenant_id}/channels", response_model=ChannelRouteResponse)
def add_channel_route(
    tenant_id: str,
    data: ChannelRouteCreateRequest,
    db: Session = Depends(get_db),
) -> ChannelRouteResponse:
    try:
        tenant_service = TenantService(db)
        with db.begin():
            route = tenant_service.add_channel_route(
                tenant_id=uuid.UUID(tenant_id),
                platform=data.platform,
                channel_identifier=data.channel_identifier,
            )
        return ChannelRouteResponse.model_validate(route)
    except ValueError as e:
        logger.error(
            "add_channel_route failed: invalid tenant_id format '%s' — %s", tenant_id, e
        )
        raise
    except Exception as e:
        logger.error("add_channel_route failed [tenant_id=%s]: %s", tenant_id, e)
        raise


@router.get("", response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_db)) -> list[TenantResponse]:
    try:
        tenant_service = TenantService(db)
        tenants = tenant_service.list_active_tenants()
        return [TenantResponse.model_validate(t) for t in tenants]
    except Exception as e:
        logger.error("list_tenants failed: %s", e)
        raise
