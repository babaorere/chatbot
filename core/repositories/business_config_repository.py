from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from config.settings import settings
from models.business_config import BusinessConfig
from repositories.base import JpaRepository

logger = logging.getLogger(__name__)

_DEFAULT_FEATURED_CONFIG: dict[str, Any] = {
    "enabled": False,
    "title": "",
    "mode": "manual",
    "product_ids": [],
}


class BusinessConfigRepository(JpaRepository[BusinessConfig]):
    def __init__(self, db: Session) -> None:
        super().__init__(BusinessConfig, db)

    def get_config(self) -> BusinessConfig:
        """
        Obtiene la configuración única del negocio (patrón singleton).
        Si no existe, la crea con valores por defecto.
        """
        try:
            config = self.db.query(BusinessConfig).first()
            if not config:
                config = BusinessConfig(
                    name=settings.business_name,
                    email=settings.business_email,
                    phone=settings.business_phone,
                    address=settings.business_address,
                    city=settings.business_city,
                    website=settings.business_website or None,
                    business_hours=self._default_business_hours(),
                    promotions_config=deepcopy(_DEFAULT_FEATURED_CONFIG),
                    best_sellers_config=deepcopy(_DEFAULT_FEATURED_CONFIG),
                    favorites_config=deepcopy(_DEFAULT_FEATURED_CONFIG),
                    estimated_attention_minutes=30,
                )
                self.save(config)
                self.db.commit()
            else:
                if config.promotions_config is None:
                    config.promotions_config = deepcopy(_DEFAULT_FEATURED_CONFIG)
                if config.best_sellers_config is None:
                    config.best_sellers_config = deepcopy(_DEFAULT_FEATURED_CONFIG)
                if config.favorites_config is None:
                    config.favorites_config = deepcopy(_DEFAULT_FEATURED_CONFIG)
                if config.estimated_attention_minutes is None:
                    config.estimated_attention_minutes = 30
            return config
        except Exception as e:
            logger.error("BusinessConfigRepository.get_config failed: %s", e)
            raise

    def _default_business_hours(self) -> dict[str, Any]:
        raw_hours: str = settings.business_hours.strip()
        if not raw_hours:
            return {
                "Lunes": {"open": "10:00", "close": "22:00"},
                "Martes": {"open": "10:00", "close": "22:00"},
                "Miércoles": {"open": "10:00", "close": "22:00"},
                "Jueves": {"open": "10:00", "close": "22:00"},
                "Viernes": {"open": "10:00", "close": "22:00"},
                "Sábado": {"open": "10:00", "close": "22:00"},
                "Domingo": {"open": "12:00", "close": "20:00"},
            }

        try:
            parsed_hours: Any = json.loads(raw_hours)
        except json.JSONDecodeError as e:
            logger.warning("Invalid BUSINESS_HOURS JSON, using defaults: %s", e)
            return self._default_business_hours()

        if isinstance(parsed_hours, dict):
            return parsed_hours

        logger.warning("BUSINESS_HOURS must be a JSON object, using defaults")
        return self._default_business_hours()
