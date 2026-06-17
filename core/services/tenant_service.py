from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from models.tenant import Tenant
from models.channel_route import ChannelRoute
from repositories.tenant_repository import TenantRepository
from repositories.channel_route_repository import ChannelRouteRepository
from exceptions.tenant_exceptions import TenantNotFoundError

logger = logging.getLogger(__name__)


class TenantService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.channel_repo = ChannelRouteRepository(db)

    def resolve_tenant(
        self,
        platform: str,
        channel_identifier: str,
    ) -> Tenant | None:
        try:
            route = self.channel_repo.find_by_platform_and_channel(
                platform, channel_identifier
            )
            if not route:
                return None

            tenant = self.tenant_repo.find_by_id_and_active(route.tenant_id)
            return tenant
        except Exception as e:
            logger.error(
                "TenantService.resolve_tenant failed [platform=%s, channel=%s]: %s",
                platform,
                channel_identifier,
                e,
            )
            raise

    def get_tenant_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        try:
            return self.tenant_repo.find_by_id_and_active(tenant_id)
        except Exception as e:
            logger.error(
                "TenantService.get_tenant_by_id failed [tenant_id=%s]: %s", tenant_id, e
            )
            raise

    def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        try:
            return self.tenant_repo.find_by_slug(slug)
        except Exception as e:
            logger.error(
                "TenantService.get_tenant_by_slug failed [slug=%s]: %s", slug, e
            )
            raise

    def create_tenant(
        self,
        slug: str,
        name: str,
        config: dict[str, Any],
    ) -> Tenant:
        try:
            if self.tenant_repo.exists_by_slug(slug):
                raise ValueError(f"Tenant with slug '{slug}' already exists")

            tenant = Tenant(slug=slug, name=name, config=config)
            return self.tenant_repo.save(tenant)
        except Exception as e:
            logger.error("TenantService.create_tenant failed [slug=%s]: %s", slug, e)
            raise

    def add_channel_route(
        self,
        tenant_id: uuid.UUID,
        platform: str,
        channel_identifier: str,
    ) -> ChannelRoute:
        try:
            tenant = self.tenant_repo.find_by_id_and_active(tenant_id)
            if not tenant:
                raise TenantNotFoundError(tenant_id)

            route = ChannelRoute(
                tenant_id=tenant_id,
                platform=platform,
                channel_identifier=channel_identifier,
            )
            return self.channel_repo.save(route)
        except Exception as e:
            logger.error(
                "TenantService.add_channel_route failed [tenant_id=%s, platform=%s]: %s",
                tenant_id,
                platform,
                e,
            )
            raise

    def list_active_tenants(self) -> list[Tenant]:
        try:
            return self.tenant_repo.find_all_active()
        except Exception as e:
            logger.error("TenantService.list_active_tenants failed: %s", e)
            raise
