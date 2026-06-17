from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from models.channel_route import ChannelRoute
from repositories.base import JpaRepository


class ChannelRouteRepository(JpaRepository[ChannelRoute]):
    def __init__(self, db: Session) -> None:
        super().__init__(ChannelRoute, db)

    def find_by_platform_and_channel(
        self,
        platform: str,
        channel_identifier: str,
    ) -> Optional[ChannelRoute]:
        return (
            self.db.query(ChannelRoute)
            .filter(
                ChannelRoute.platform == platform,
                ChannelRoute.channel_identifier == channel_identifier,
            )
            .first()
        )

    def find_by_tenant_id(self, tenant_id: uuid.UUID) -> list[ChannelRoute]:
        return (
            self.db.query(ChannelRoute)
            .filter(ChannelRoute.tenant_id == tenant_id)
            .all()
        )

    def exists_by_platform_and_channel(
        self,
        platform: str,
        channel_identifier: str,
    ) -> bool:
        return (
            self.db.query(ChannelRoute)
            .filter(
                ChannelRoute.platform == platform,
                ChannelRoute.channel_identifier == channel_identifier,
            )
            .first()
            is not None
        )
