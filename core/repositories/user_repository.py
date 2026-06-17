from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from models.user import User
from repositories.base import JpaRepository


class UserRepository(JpaRepository[User]):
    def __init__(self, db: Session) -> None:
        super().__init__(User, db)

    def find_by_external_id_and_platform(
        self,
        external_id: str,
        platform: str,
        tenant_id: uuid.UUID,
    ) -> Optional[User]:
        return (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.external_id == external_id,
                User.platform == platform,
            )
            .first()
        )

    def find_by_tenant_id(
        self,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        return (
            self.db.query(User)
            .filter(User.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def exists_by_external_id_and_platform(
        self,
        external_id: str,
        platform: str,
        tenant_id: uuid.UUID,
    ) -> bool:
        return (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.external_id == external_id,
                User.platform == platform,
            )
            .first()
            is not None
        )
