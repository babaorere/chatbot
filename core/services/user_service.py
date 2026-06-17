from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from models.user import User
from repositories.user_repository import UserRepository
from exceptions.user_exceptions import UserNotFoundError

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Session, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repo = UserRepository(db)

    def get_or_create(
        self,
        external_id: str,
        platform: str,
        display_name: str | None = None,
    ) -> User:
        try:
            user = self.repo.find_by_external_id_and_platform(
                external_id, platform, self.tenant_id
            )
            if user:
                return user

            user = User(
                tenant_id=self.tenant_id,
                external_id=external_id,
                platform=platform,
                display_name=display_name,
            )
            return self.repo.save(user)
        except Exception as e:
            logger.error(
                "UserService.get_or_create failed [external_id=%s, platform=%s]: %s",
                external_id,
                platform,
                e,
            )
            raise

    def get_by_id(self, user_id: int) -> User | None:
        try:
            user = self.repo.find_by_id(user_id)
            if user and user.tenant_id != self.tenant_id:
                return None
            return user
        except Exception as e:
            logger.error("UserService.get_by_id failed [user_id=%s]: %s", user_id, e)
            raise

    def get_required_by_id(self, user_id: int) -> User:
        try:
            user = self.get_by_id(user_id)
            if not user:
                raise UserNotFoundError(user_id)
            return user
        except Exception as e:
            logger.error(
                "UserService.get_required_by_id failed [user_id=%s]: %s", user_id, e
            )
            raise

    def list_users(self, skip: int = 0, limit: int = 50) -> list[User]:
        try:
            return self.repo.find_by_tenant_id(self.tenant_id, skip=skip, limit=limit)
        except Exception as e:
            logger.error("UserService.list_users failed: %s", e)
            raise
