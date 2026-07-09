from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from config.database import SessionLocal
from domain.business_config import (
    BusinessHoursConfig,
    FeaturedProductsConfig,
    normalize_business_hours_config,
    normalize_featured_products_config,
)
from services.business_config_service import BusinessConfigService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BusinessConfigSnapshot:
    name: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    business_hours: BusinessHoursConfig = field(
        default_factory=lambda: BusinessHoursConfig.model_validate({})
    )
    promotions_config: FeaturedProductsConfig = field(
        default_factory=FeaturedProductsConfig
    )
    best_sellers_config: FeaturedProductsConfig = field(
        default_factory=FeaturedProductsConfig
    )
    favorites_config: FeaturedProductsConfig = field(
        default_factory=FeaturedProductsConfig
    )
    estimated_attention_minutes: int | None = None
    human_agent_available: bool = True
    loaded_at: float = 0.0
    version: int = 0


_business_config_snapshot = BusinessConfigSnapshot()
_human_agent_cache: dict[str, Any] = {"value": True, "expires_at": 0.0}


def prime_business_config_cache(
    *,
    config: Any | None = None,
    log_timing: Any | None = None,
) -> BusinessConfigSnapshot:
    global _business_config_snapshot, _human_agent_cache
    started_at = time.perf_counter()
    db = None
    try:
        if config is None:
            db = SessionLocal()
            config = BusinessConfigService(db).get_config()

        next_snapshot = BusinessConfigSnapshot(
            name=str(getattr(config, "name", "") or ""),
            phone=str(getattr(config, "phone", "") or ""),
            address=str(getattr(config, "address", "") or ""),
            city=str(getattr(config, "city", "") or ""),
            business_hours=normalize_business_hours_config(
                getattr(config, "business_hours", {}) or {}
            ),
            promotions_config=normalize_featured_products_config(
                getattr(config, "promotions_config", {}) or {}
            ),
            best_sellers_config=normalize_featured_products_config(
                getattr(config, "best_sellers_config", {}) or {}
            ),
            favorites_config=normalize_featured_products_config(
                getattr(config, "favorites_config", {}) or {}
            ),
            estimated_attention_minutes=getattr(
                config,
                "estimated_attention_minutes",
                None,
            ),
            human_agent_available=bool(getattr(config, "human_agent_available", True)),
            loaded_at=time.time(),
            version=_business_config_snapshot.version + 1,
        )
        _business_config_snapshot = next_snapshot
        _human_agent_cache = {
            "value": next_snapshot.human_agent_available,
            "expires_at": time.time() + 300,
        }
        if log_timing is not None:
            log_timing(
                trace_id="business-config-cache-prime",
                stage="business_config_cache_primed",
                started_at=started_at,
                extra=f"version={next_snapshot.version}",
            )
        return next_snapshot
    except Exception as exc:
        logger.exception("Failed to prime business config cache")
        raise RuntimeError("Failed to prime business config cache") from exc
    finally:
        if db is not None:
            db.close()


def get_business_config_snapshot(
    *,
    log_timing: Any | None = None,
) -> BusinessConfigSnapshot:
    if _business_config_snapshot.version > 0:
        logger.info(
            "[telegram_cache] key=business_config hit version=%d age_seconds=%.2f",
            _business_config_snapshot.version,
            time.time() - _business_config_snapshot.loaded_at,
        )
        return _business_config_snapshot

    logger.info("[telegram_cache] key=business_config miss")
    return prime_business_config_cache(log_timing=log_timing)


def prime_human_agent_cache(value: bool, ttl_seconds: int = 300) -> None:
    global _human_agent_cache
    _human_agent_cache = {
        "value": value,
        "expires_at": time.time() + ttl_seconds,
    }


def get_human_agent_available(
    *,
    log_timing: Any | None = None,
) -> bool:
    now = time.time()
    if now < _human_agent_cache["expires_at"]:
        logger.info(
            "[telegram_cache] key=human_agent_available hit ttl_remaining=%.2f value=%s",
            _human_agent_cache["expires_at"] - now,
            _human_agent_cache["value"],
        )
        return _human_agent_cache["value"]

    logger.info("[telegram_cache] key=human_agent_available miss")
    db = SessionLocal()
    try:
        config = BusinessConfigService(db).get_config()
        snapshot = prime_business_config_cache(config=config, log_timing=log_timing)
        return snapshot.human_agent_available
    except Exception as exc:
        logger.exception("Failed to resolve human agent availability")
        raise RuntimeError("Failed to resolve human agent availability") from exc
    finally:
        db.close()
