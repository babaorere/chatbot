from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config.database import get_db, set_tenant_context
from models.tenant import Tenant
from services import (
    TenantService,
    KBService,
    ProductService,
    UserService,
    ConversationService,
)
from dtos.request import (
    TenantProfileUpdateRequest,
    ProductCreateRequest,
    ProductUpdateRequest,
    KBEntryCreateRequest,
    KBEntryUpdateRequest,
    KBSearchRequest,
)
from dtos.response import (
    TenantProfileResponse,
    ProductResponse,
    KBEntryResponse,
    KBSearchResponse,
    KBSearchResultItem,
    ChannelRouteResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/me", tags=["tenant-portal"])


def get_current_tenant(request: Request, db: Session = Depends(get_db)) -> Tenant:
    tenant_id_header = request.headers.get("X-Tenant-ID")
    if not tenant_id_header:
        logger.warning("Missing X-Tenant-ID header on tenant portal request")
        raise HTTPException(401, "Missing X-Tenant-ID header")

    try:
        tenant_id = uuid.UUID(tenant_id_header)
    except ValueError as e:
        logger.warning("Invalid X-Tenant-ID format: %s — %s", tenant_id_header, e)
        raise HTTPException(401, "Invalid X-Tenant-ID format") from e

    tenant_service = TenantService(db)
    tenant = tenant_service.get_tenant_by_id(tenant_id)
    if not tenant:
        logger.warning("Tenant not found: %s", tenant_id)
        raise HTTPException(403, f"Tenant {tenant_id} not found or inactive")

    return tenant


# ── Profile ──────────────────────────────────────────────────────────────────


@router.get("/profile", response_model=TenantProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> TenantProfileResponse:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))
        return TenantProfileResponse.model_validate(tenant)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_profile failed: %s", e)
        raise


@router.put("/profile", response_model=TenantProfileResponse)
def update_profile(
    data: TenantProfileUpdateRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> TenantProfileResponse:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        with db.begin():
            if data.name is not None:
                tenant.name = data.name
            if data.email is not None:
                tenant.email = data.email
            if data.phone is not None:
                tenant.phone = data.phone
            if data.address is not None:
                tenant.address = data.address
            if data.city is not None:
                tenant.city = data.city
            if data.website is not None:
                tenant.website = data.website
            if data.logo_url is not None:
                tenant.logo_url = data.logo_url
            if data.business_hours is not None:
                tenant.business_hours = data.business_hours

            db.flush()
            db.refresh(tenant)

        return TenantProfileResponse.model_validate(tenant)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_profile failed: %s", e)
        raise


# ── Channels ─────────────────────────────────────────────────────────────────


@router.get("/channels", response_model=list[ChannelRouteResponse])
def list_channels(
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[ChannelRouteResponse]:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        tenant_service = TenantService(db)
        routes = tenant_service.channel_repo.find_by_tenant_id(tenant.id)
        return [ChannelRouteResponse.model_validate(r) for r in routes]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_channels failed: %s", e)
        raise


# ── Products ─────────────────────────────────────────────────────────────────


@router.get("/products", response_model=list[ProductResponse])
def list_products(
    category: str | None = None,
    available_only: bool = False,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[ProductResponse]:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        product_svc = ProductService(db, tenant.id)
        products = product_svc.list_products(
            category=category,
            available_only=available_only,
            skip=skip,
            limit=limit,
        )
        return [ProductResponse.model_validate(p) for p in products]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_products failed: %s", e)
        raise


@router.post("/products", response_model=ProductResponse)
def create_product(
    data: ProductCreateRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> ProductResponse:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        product_svc = ProductService(db, tenant.id)
        with db.begin():
            product = product_svc.create_product(
                name=data.name,
                description=data.description,
                price=data.price,
                stock=data.stock,
                category=data.category,
                is_available=data.is_available,
            )
        return ProductResponse.model_validate(product)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_product failed: %s", e)
        raise


@router.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: str,
    data: ProductUpdateRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> ProductResponse:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        product_svc = ProductService(db, tenant.id)
        with db.begin():
            product = product_svc.update_product(
                product_id=uuid.UUID(product_id),
                name=data.name,
                description=data.description,
                price=data.price,
                stock=data.stock,
                category=data.category,
                is_available=data.is_available,
            )
        return ProductResponse.model_validate(product)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_product failed: %s", e)
        raise


@router.delete("/products/{product_id}")
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> dict:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        product_svc = ProductService(db, tenant.id)
        with db.begin():
            deleted = product_svc.delete_product(uuid.UUID(product_id))
        if not deleted:
            raise HTTPException(404, "Product not found")
        return {"status": "deleted", "id": product_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_product failed: %s", e)
        raise


@router.get("/products/categories", response_model=list[str])
def get_product_categories(
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[str]:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        product_svc = ProductService(db, tenant.id)
        return product_svc.get_categories()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_product_categories failed: %s", e)
        raise


# ── Knowledge Base ───────────────────────────────────────────────────────────


@router.get("/kb", response_model=list[KBEntryResponse])
def list_kb_entries(
    category: str | None = None,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[KBEntryResponse]:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        kb_svc = KBService(db, tenant.id)
        entries = kb_svc.list_entries(
            category=category,
            active_only=active_only,
            skip=skip,
            limit=limit,
        )
        return [KBEntryResponse.model_validate(e) for e in entries]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_kb_entries failed: %s", e)
        raise


@router.post("/kb", response_model=KBEntryResponse)
def create_kb_entry(
    data: KBEntryCreateRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> KBEntryResponse:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        kb_svc = KBService(db, tenant.id)
        with db.begin():
            entry = kb_svc.create_entry(
                category=data.category,
                title=data.title,
                content=data.content,
            )
        return KBEntryResponse.model_validate(entry)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_kb_entry failed: %s", e)
        raise


@router.put("/kb/{entry_id}", response_model=KBEntryResponse)
def update_kb_entry(
    entry_id: str,
    data: KBEntryUpdateRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> KBEntryResponse:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        kb_svc = KBService(db, tenant.id)
        with db.begin():
            entry = kb_svc.update_entry(
                entry_id=uuid.UUID(entry_id),
                category=data.category,
                title=data.title,
                content=data.content,
                is_active=data.is_active,
            )
        return KBEntryResponse.model_validate(entry)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_kb_entry failed: %s", e)
        raise


@router.delete("/kb/{entry_id}")
def delete_kb_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> dict:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        kb_svc = KBService(db, tenant.id)
        with db.begin():
            deleted = kb_svc.delete_entry(uuid.UUID(entry_id))
        if not deleted:
            raise HTTPException(404, "KB entry not found")
        return {"status": "deleted", "id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_kb_entry failed: %s", e)
        raise


@router.post("/kb/search", response_model=KBSearchResponse)
def search_kb(
    data: KBSearchRequest,
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> KBSearchResponse:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        kb_svc = KBService(db, tenant.id)
        results = kb_svc.search(
            query=data.query, top_k=data.top_k, category=data.category
        )
        return KBSearchResponse(
            query=data.query,
            results=[KBSearchResultItem(**r) for r in results],
            count=len(results),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("search_kb failed: %s", e)
        raise


@router.get("/kb/categories", response_model=list[str])
def get_kb_categories(
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> list[str]:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        kb_svc = KBService(db, tenant.id)
        return kb_svc.get_categories()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_kb_categories failed: %s", e)
        raise


# ── Users & Conversations (read-only) ────────────────────────────────────────


@router.get("/users/count")
def get_user_count(
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> dict:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        user_svc = UserService(db, tenant.id)
        count = user_svc.repo.count_by_tenant(tenant.id)
        return {"count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_user_count failed: %s", e)
        raise


@router.get("/conversations/count")
def get_conversation_count(
    db: Session = Depends(get_db),
    fastapi_request: Request = None,
) -> dict:
    try:
        tenant = get_current_tenant(fastapi_request, db)
        set_tenant_context(db, str(tenant.id))

        conv_svc = ConversationService(db, tenant.id)
        count = conv_svc.repo.count_by_tenant(tenant.id)
        return {"count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_conversation_count failed: %s", e)
        raise
