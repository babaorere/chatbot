from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.security import get_admin_api_key
from config.database import get_db
from models.user import User
from models.conversation import Conversation
from models.knowledge_base import KnowledgeBase
from models.product import Product
from repositories.system_setting_repository import (
    SystemSettingRepository as SysSettingRepo,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_admin_api_key)],
)


# ── System Settings ──────────────────────────────────────────────────────────


@router.get("/settings")
def get_all_settings(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        repo = SysSettingRepo(db)
        return repo.get_all_settings()
    except Exception as e:
        logger.error("admin.get_all_settings failed: %s", e)
        raise HTTPException(500, f"Failed to retrieve settings: {e}")


@router.put("/settings/{key}")
def update_setting(
    key: str,
    data: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict:
    try:
        repo = SysSettingRepo(db)
        with db.begin():
            setting = repo.set_value(
                key=key,
                value=data.get("value"),
                description=data.get("description"),
            )
        return {
            "key": setting.key,
            "value": setting.value,
            "description": setting.description,
        }
    except Exception as e:
        logger.error("admin.update_setting failed [key=%s]: %s", key, e)
        raise HTTPException(500, f"Failed to update setting: {e}")


# ── Metrics ──────────────────────────────────────────────────────────────────


@router.get("/health/metrics")
def get_system_metrics(
    db: Session = Depends(get_db),
) -> dict:
    try:
        total_users = db.query(User).count()
        total_conversations = db.query(Conversation).count()
        total_kb_entries = (
            db.query(KnowledgeBase).filter(KnowledgeBase.is_active).count()
        )
        total_products = db.query(Product).count()

        return {
            "total_users": total_users,
            "total_conversations": total_conversations,
            "total_kb_entries": total_kb_entries,
            "total_products": total_products,
        }
    except Exception as e:
        logger.error("admin.get_system_metrics failed: %s", e)
        raise HTTPException(500, f"Failed to retrieve metrics: {e}")
