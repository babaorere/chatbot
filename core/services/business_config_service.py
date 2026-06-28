from __future__ import annotations

import logging
from typing import Any
from sqlalchemy.orm import Session
from models.business_config import BusinessConfig
from repositories.business_config_repository import BusinessConfigRepository

logger = logging.getLogger(__name__)


class BusinessConfigService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = BusinessConfigRepository(db)

    def get_config(self) -> BusinessConfig:
        try:
            return self.repo.get_config()
        except Exception as e:
            logger.error("BusinessConfigService.get_config failed: %s", e)
            raise

    def update_config(
        self,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        city: str | None = None,
        website: str | None = None,
        logo_url: str | None = None,
        business_hours: dict[str, Any] | None = None,
        human_agent_available: bool | None = None,
    ) -> BusinessConfig:
        try:
            config = self.repo.get_config()
            if name is not None:
                config.name = name
            if email is not None:
                config.email = email
            if phone is not None:
                config.phone = phone
            if address is not None:
                config.address = address
            if city is not None:
                config.city = city
            if website is not None:
                config.website = website
            if logo_url is not None:
                config.logo_url = logo_url
            if business_hours is not None:
                config.business_hours = business_hours
            if human_agent_available is not None:
                config.human_agent_available = human_agent_available

            self.db.flush()
            self.db.refresh(config)
            return config
        except Exception as e:
            logger.error("BusinessConfigService.update_config failed: %s", e)
            raise
