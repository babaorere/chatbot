from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session
from config.settings import settings
from models.system_admin import SystemAdmin
from repositories.system_setting_repository import SystemSettingRepository
from services.telegram_service import send_telegram_message

logger = logging.getLogger(__name__)


class AlertService:
    LATENCY_THRESHOLD_SECONDS = 10.0

    @staticmethod
    async def notify_critical_issue(
        db: Session, title: str, details: str, alert_type: str = "error"
    ) -> None:
        """Envía una notificación a todos los administradores registrados según sus preferencias."""
        admins = db.query(SystemAdmin).all()

        bot_token = settings.telegram_bot_token
        alert_text = f"🚨 *ALERTA CRÍTICA: {title}*\n\n{details}\n\n🏷️ *Tipo:* `{alert_type}`"
        tasks = []
        notification_targets = 0

        for admin in admins:
            if admin.alert_types and alert_type not in admin.alert_types:
                logger.debug(
                    "Admin %s ignora alerta tipo %s por preferencia",
                    admin.name,
                    alert_type,
                )
                continue

            if admin.notify_telegram and admin.telegram_chat_id:
                notification_targets += 1
                if not bot_token:
                    raise RuntimeError(
                        "Cannot send Telegram alert because telegram_bot_token is missing."
                    )
                tasks.append(
                    send_telegram_message(bot_token, admin.telegram_chat_id, alert_text)
                )

            if admin.notify_email and admin.email:
                raise RuntimeError(
                    f"Email alert channel is configured for {admin.name}, but no email delivery implementation exists."
                )

            if admin.notify_whatsapp and admin.whatsapp_phone:
                raise RuntimeError(
                    f"WhatsApp alert channel is configured for {admin.name}, but no WhatsApp delivery implementation exists."
                )

        if not tasks and not admins:
            logger.info("No system admins registered. Falling back to settings key.")
            repo = SystemSettingRepository(db)
            chat_ids = repo.get_value("admin_chat_ids")
            if chat_ids and isinstance(chat_ids, list):
                if not bot_token:
                    raise RuntimeError(
                        "Cannot send Telegram alert because telegram_bot_token is missing."
                    )
                notification_targets += len(chat_ids)
                tasks = [
                    send_telegram_message(bot_token, chat_id, alert_text)
                    for chat_id in chat_ids
                ]

        if not notification_targets:
            raise RuntimeError(
                "No alert recipients configured for critical issue notification."
            )

        if tasks:
            await asyncio.gather(*tasks)

    @staticmethod
    async def check_llm_latency(
        db: Session, duration: float, user_id: str, session_id: str
    ) -> None:
        """Evalúa si la latencia del LLM es crítica y alerta a los administradores."""
        if duration >= AlertService.LATENCY_THRESHOLD_SECONDS:
            title = "Latencia Crítica de LLM"
            details = (
                f"El tiempo de respuesta del LLM excedió el umbral.\n\n"
                f"⏱️ *Duración:* {duration:.2f} segundos\n"
                f"👤 *User ID:* `{user_id}`\n"
                f"💬 *Session ID:* `{session_id}`"
            )
            await AlertService.notify_critical_issue(
                db, title, details, alert_type="latency"
            )
