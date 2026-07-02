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
from models.system_admin import SystemAdmin
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
    """Devuelve el conjunto completo de system settings administrables."""
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
    """Actualiza el valor y la descripción de una system setting existente."""
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
    """Entrega métricas agregadas del sistema para paneles administrativos."""
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


# ── System Admins CRUD ─────────────────────────────────────────────────────────


@router.get("/system-admins")
def get_system_admins(
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lista todos los administradores del sistema."""
    try:
        admins = db.query(SystemAdmin).all()
        return [admin.to_dict() for admin in admins]
    except Exception as e:
        logger.error("admin.get_system_admins failed: %s", e)
        raise HTTPException(500, f"Failed to list system admins: {e}")


@router.post("/system-admins")
def create_system_admin(
    data: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict:
    """Crea un nuevo administrador y sus preferencias de alertas."""
    try:
        with db.begin():
            admin = SystemAdmin(
                name=data.get("name"),
                email=data.get("email"),
                telegram_chat_id=data.get("telegram_chat_id"),
                whatsapp_phone=data.get("whatsapp_phone"),
                notify_email=data.get("notify_email", False),
                notify_telegram=data.get("notify_telegram", True),
                notify_whatsapp=data.get("notify_whatsapp", False),
                alert_types=data.get("alert_types", []),
            )
            db.add(admin)
        db.refresh(admin)
        return admin.to_dict()
    except Exception as e:
        logger.error("admin.create_system_admin failed: %s", e)
        raise HTTPException(500, f"Failed to create system admin: {e}")


@router.put("/system-admins/{admin_id}")
def update_system_admin(
    admin_id: int,
    data: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict:
    """Actualiza un administrador existente y sus preferencias de alertas."""
    try:
        with db.begin():
            admin = db.query(SystemAdmin).filter(SystemAdmin.id == admin_id).first()
            if not admin:
                raise HTTPException(404, "System admin not found")
            admin.name = data.get("name", admin.name)
            admin.email = data.get("email", admin.email)
            admin.telegram_chat_id = data.get("telegram_chat_id", admin.telegram_chat_id)
            admin.whatsapp_phone = data.get("whatsapp_phone", admin.whatsapp_phone)
            admin.notify_email = data.get("notify_email", admin.notify_email)
            admin.notify_telegram = data.get("notify_telegram", admin.notify_telegram)
            admin.notify_whatsapp = data.get("notify_whatsapp", admin.notify_whatsapp)
            admin.alert_types = data.get("alert_types", admin.alert_types)
        db.refresh(admin)
        return admin.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.update_system_admin failed [id=%s]: %s", admin_id, e)
        raise HTTPException(500, f"Failed to update system admin: {e}")


@router.delete("/system-admins/{admin_id}")
def delete_system_admin(
    admin_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Elimina un administrador."""
    try:
        with db.begin():
            admin = db.query(SystemAdmin).filter(SystemAdmin.id == admin_id).first()
            if not admin:
                raise HTTPException(404, "System admin not found")
            db.delete(admin)
        return {"status": "success", "message": "System admin deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("admin.delete_system_admin failed [id=%s]: %s", admin_id, e)
        raise HTTPException(500, f"Failed to delete system admin: {e}")
