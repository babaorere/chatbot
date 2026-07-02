from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any
from sqlalchemy.orm import Session
from models.business_config import BusinessConfig
from repositories.business_config_repository import BusinessConfigRepository

logger = logging.getLogger(__name__)

_DEFAULT_FEATURED_CONFIG: dict[str, Any] = {
    "enabled": False,
    "title": "",
    "mode": "manual",
    "product_ids": [],
}


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
        promotions_config: dict[str, Any] | None = None,
        best_sellers_config: dict[str, Any] | None = None,
        favorites_config: dict[str, Any] | None = None,
        estimated_attention_minutes: int | None = None,
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
            if promotions_config is not None:
                config.promotions_config = self._normalize_featured_config(
                    promotions_config
                )
            if best_sellers_config is not None:
                config.best_sellers_config = self._normalize_featured_config(
                    best_sellers_config
                )
            if favorites_config is not None:
                config.favorites_config = self._normalize_featured_config(
                    favorites_config
                )
            if estimated_attention_minutes is not None:
                config.estimated_attention_minutes = self._normalize_attention_minutes(
                    estimated_attention_minutes
                )
            if human_agent_available is not None:
                config.human_agent_available = human_agent_available

            self.db.flush()
            self.db.refresh(config)
            return config
        except Exception as e:
            logger.error("BusinessConfigService.update_config failed: %s", e)
            raise

    def _normalize_featured_config(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = {**deepcopy(_DEFAULT_FEATURED_CONFIG), **config}
        product_ids = normalized.get("product_ids") or []
        normalized["product_ids"] = [str(product_id) for product_id in product_ids]
        normalized["enabled"] = bool(normalized.get("enabled", False))
        normalized["mode"] = (
            "automatic"
            if normalized.get("mode") == "automatic"
            else "manual"
        )
        normalized["title"] = str(normalized.get("title", "")).strip()
        return normalized

    def _normalize_attention_minutes(self, value: int) -> int:
        minutes = int(value)
        if minutes < 1:
            raise ValueError("estimated_attention_minutes must be at least 1")
        if minutes > 1440:
            raise ValueError("estimated_attention_minutes must be at most 1440")
        return minutes
