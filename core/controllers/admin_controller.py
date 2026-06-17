from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config.database import get_db
from services import TenantService
from repositories.system_setting_repository import (
    SystemSettingRepository as SysSettingRepo,
)
from dtos.request import TenantCreateRequest, ChannelRouteCreateRequest
from dtos.response import TenantResponse, ChannelRouteResponse, TenantProfileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Tenant Management ────────────────────────────────────────────────────────


@router.get("/tenants", response_model=list[TenantResponse])
def list_all_tenants(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[TenantResponse]:
    try:
        tenant_service = TenantService(db)
        tenants = tenant_service.tenant_repo.find_all(skip=skip, limit=limit)
        return [TenantResponse.model_validate(t) for t in tenants]
    except Exception as e:
        logger.error("admin.list_all_tenants failed: %s", e)
        raise


@router.post("/tenants", response_model=TenantResponse)
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
        logger.error("admin.create_tenant failed [slug=%s]: %s", data.slug, e)
        raise


@router.get("/tenants/{tenant_id}", response_model=TenantProfileResponse)
def get_tenant_detail(
    tenant_id: str,
    db: Session = Depends(get_db),
) -> TenantProfileResponse:
    try:
        tenant_service = TenantService(db)
        tenant = tenant_service.get_tenant_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise HTTPException(404, f"Tenant {tenant_id} not found")
        return TenantProfileResponse.model_validate(tenant)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.get_tenant_detail failed [id=%s]: %s", tenant_id, e)
        raise


@router.put("/tenants/{tenant_id}", response_model=TenantProfileResponse)
def update_tenant(
    tenant_id: str,
    data: dict[str, Any],
    db: Session = Depends(get_db),
) -> TenantProfileResponse:
    try:
        tenant_service = TenantService(db)
        tenant = tenant_service.get_tenant_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise HTTPException(404, f"Tenant {tenant_id} not found")

        with db.begin():
            if "name" in data:
                tenant.name = data["name"]
            if "slug" in data:
                tenant.slug = data["slug"]
            if "status" in data:
                tenant.status = data["status"]
            if "email" in data:
                tenant.email = data["email"]
            if "phone" in data:
                tenant.phone = data["phone"]
            if "address" in data:
                tenant.address = data["address"]
            if "city" in data:
                tenant.city = data["city"]
            if "website" in data:
                tenant.website = data["website"]
            if "logo_url" in data:
                tenant.logo_url = data["logo_url"]
            if "business_hours" in data:
                tenant.business_hours = data["business_hours"]

            db.flush()
            db.refresh(tenant)

        return TenantProfileResponse.model_validate(tenant)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.update_tenant failed [id=%s]: %s", tenant_id, e)
        raise


@router.patch("/tenants/{tenant_id}/status")
def update_tenant_status(
    tenant_id: str,
    status: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        if status not in ("active", "inactive"):
            raise HTTPException(400, "Status must be 'active' or 'inactive'")

        tenant_service = TenantService(db)
        tenant = tenant_service.get_tenant_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise HTTPException(404, f"Tenant {tenant_id} not found")

        with db.begin():
            tenant.status = status
            db.flush()

        return {"status": "updated", "tenant_id": tenant_id, "new_status": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.update_tenant_status failed [id=%s]: %s", tenant_id, e)
        raise


@router.delete("/tenants/{tenant_id}")
def delete_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        tenant_service = TenantService(db)
        tenant = tenant_service.get_tenant_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise HTTPException(404, f"Tenant {tenant_id} not found")

        with db.begin():
            db.delete(tenant)

        return {"status": "deleted", "tenant_id": tenant_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.delete_tenant failed [id=%s]: %s", tenant_id, e)
        raise


# ── Agent Configuration ──────────────────────────────────────────────────────


@router.get("/tenants/{tenant_id}/agent")
def get_agent_config(
    tenant_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        tenant_service = TenantService(db)
        tenant = tenant_service.get_tenant_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise HTTPException(404, f"Tenant {tenant_id} not found")

        return {
            "tenant_id": str(tenant.id),
            "slug": tenant.slug,
            "model": tenant.get_model(),
            "instruction": tenant.get_instruction(),
            "has_api_key": bool(tenant.get_api_key()),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.get_agent_config failed [id=%s]: %s", tenant_id, e)
        raise


@router.put("/tenants/{tenant_id}/agent")
def update_agent_config(
    tenant_id: str,
    data: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict:
    try:
        tenant_service = TenantService(db)
        tenant = tenant_service.get_tenant_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise HTTPException(404, f"Tenant {tenant_id} not found")

        with db.begin():
            config = tenant.config.copy()
            if "instruction" in data:
                config["instruction"] = data["instruction"]
            if "model" in data:
                config["model"] = data["model"]
            if "api_key" in data:
                config["api_key"] = data["api_key"]

            tenant.config = config
            db.flush()

        return {
            "status": "updated",
            "tenant_id": tenant_id,
            "model": tenant.get_model(),
            "has_api_key": bool(tenant.get_api_key()),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.update_agent_config failed [id=%s]: %s", tenant_id, e)
        raise


# ── Channel Management ───────────────────────────────────────────────────────


@router.post("/tenants/{tenant_id}/channels", response_model=ChannelRouteResponse)
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
    except Exception as e:
        logger.error("admin.add_channel_route failed [tenant=%s]: %s", tenant_id, e)
        raise


@router.delete("/tenants/{tenant_id}/channels/{route_id}")
def delete_channel_route(
    tenant_id: str,
    route_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        tenant_service = TenantService(db)
        route = tenant_service.channel_repo.find_by_id_and_tenant(
            uuid.UUID(route_id), uuid.UUID(tenant_id)
        )
        if not route:
            raise HTTPException(404, "Channel route not found")

        with db.begin():
            db.delete(route)

        return {"status": "deleted", "route_id": route_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "admin.delete_channel_route failed [tenant=%s, route=%s]: %s",
            tenant_id,
            route_id,
            e,
        )
        raise


# ── System Settings ──────────────────────────────────────────────────────────


@router.get("/settings")
def get_all_settings(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        repo = SysSettingRepo(db)
        return repo.get_all_settings()
    except Exception as e:
        logger.error("admin.get_all_settings failed: %s", e)
        raise


@router.put("/settings/{key}")
def update_setting(
    key: str,
    data: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict:
    try:
        repo = SysSettingRepo(db)
        with db.begin():
            setting = repo.set_value(
                key=key,
                value=data.get("value"),
                description=data.get("description"),
            )
        return {
            "key": setting.key,
            "value": setting.value,
            "description": setting.description,
        }
    except Exception as e:
        logger.error("admin.update_setting failed [key=%s]: %s", key, e)
        raise


# ── Metrics ──────────────────────────────────────────────────────────────────


@router.get("/health/metrics")
def get_system_metrics(
    db: Session = Depends(get_db),
) -> dict:
    try:
        tenant_service = TenantService(db)
        tenants = tenant_service.list_active_tenants()

        total_users = 0
        total_conversations = 0
        total_kb_entries = 0
        total_products = 0

        for tenant in tenants:
            total_users += (
                tenant_service.tenant_repo.db.query(
                    tenant_service.tenant_repo.db.query.__self__.query
                )
                .filter_by(tenant_id=tenant.id)
                .count()
            )

        return {
            "active_tenants": len(tenants),
            "total_tenants": tenant_service.tenant_repo.count(),
            "total_users": total_users,
            "total_conversations": total_conversations,
            "total_kb_entries": total_kb_entries,
            "total_products": total_products,
        }
    except Exception as e:
        logger.error("admin.get_system_metrics failed: %s", e)
        raise
