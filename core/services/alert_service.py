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
        try:
            # 1. Obtener administradores de la tabla system_admins
            admins = db.query(SystemAdmin).all()

            bot_token = settings.telegram_bot_token
            alert_text = f"🚨 *ALERTA CRÍTICA: {title}*\n\n{details}\n\n🏷️ *Tipo:* `{alert_type}`"
            tasks = []

            for admin in admins:
                # Filtrar por tipo de alerta si el admin ha especificado preferencias
                # Si alert_types está vacío, asume que recibe todo
                if admin.alert_types and alert_type not in admin.alert_types:
                    logger.debug(
                        "Admin %s ignora alerta tipo %s por preferencia",
                        admin.name,
                        alert_type,
                    )
                    continue

                # Canal: Telegram
                if admin.notify_telegram and admin.telegram_chat_id:
                    if bot_token:
                        tasks.append(
                            send_telegram_message(
                                bot_token, admin.telegram_chat_id, alert_text
                            )
                        )
                    else:
                        logger.warning(
                            "Cannot send Telegram alert. Bot token missing."
                        )

                # Canal: Email (Placeholder para futura versión / extensión)
                if admin.notify_email and admin.email:
                    logger.info(
                        "[EMAIL ALERT SENT] to %s (%s): %s",
                        admin.name,
                        admin.email,
                        title,
                    )

                # Canal: WhatsApp (Placeholder escalable para próxima versión)
                if admin.notify_whatsapp and admin.whatsapp_phone:
                    logger.info(
                        "[WHATSAPP ALERT SENT] to %s (%s): %s",
                        admin.name,
                        admin.whatsapp_phone,
                        title,
                    )

            # 2. Fallback: Si no hay administradores en la tabla system_admins, usar settings
            if not tasks and not admins:
                logger.info("No system admins registered. Falling back to settings key.")
                repo = SystemSettingRepository(db)
                chat_ids = repo.get_value("admin_chat_ids")
                if chat_ids and isinstance(chat_ids, list) and bot_token:
                    tasks = [
                        send_telegram_message(bot_token, chat_id, alert_text)
                        for chat_id in chat_ids
                    ]

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error("Failed to notify admins of critical issue: %s", e)

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
