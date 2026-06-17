from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from models.tenant import Tenant
from repositories.base import JpaRepository


class TenantRepository(JpaRepository[Tenant]):
    def __init__(self, db: Session) -> None:
        super().__init__(Tenant, db)

    def find_by_id_and_active(self, tenant_id: uuid.UUID) -> Optional[Tenant]:
        return (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id, Tenant.status == "active")
            .first()
        )

    def find_by_slug(self, slug: str) -> Optional[Tenant]:
        return self.db.query(Tenant).filter(Tenant.slug == slug).first()

    def find_all_active(self) -> list[Tenant]:
        return self.db.query(Tenant).filter(Tenant.status == "active").all()

    def exists_by_slug(self, slug: str) -> bool:
        return self.db.query(Tenant).filter(Tenant.slug == slug).first() is not None
