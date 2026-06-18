from __future__ import annotations

import logging
from typing import Optional
from sqlalchemy.orm import Session
from models.user import User
from repositories.base import JpaRepository

logger = logging.getLogger(__name__)


class UserRepository(JpaRepository[User]):
    def __init__(self, db: Session) -> None:
        super().__init__(User, db)

    def find_by_external_id_and_platform(
        self,
        external_id: str,
        platform: str,
    ) -> Optional[User]:
        try:
            return (
                self.db.query(User)
                .filter(
                    User.external_id == external_id,
                    User.platform == platform,
                )
                .first()
            )
        except Exception as e:
            logger.error(
                "UserRepository.find_by_external_id_and_platform failed [external_id=%s, platform=%s]: %s",
                external_id,
                platform,
                e,
            )
            raise

    def find_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        try:
            return self.db.query(User).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error("UserRepository.find_all failed: %s", e)
            raise

    def exists_by_external_id_and_platform(
        self,
        external_id: str,
        platform: str,
    ) -> bool:
        try:
            return (
                self.db.query(User)
                .filter(
                    User.external_id == external_id,
                    User.platform == platform,
                )
                .first()
                is not None
            )
        except Exception as e:
            logger.error(
                "UserRepository.exists_by_external_id_and_platform failed [external_id=%s, platform=%s]: %s",
                external_id,
                platform,
                e,
            )
            raise
