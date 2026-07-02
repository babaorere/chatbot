from __future__ import annotations

from sqlalchemy import Column, Integer, String, Boolean, JSON
from config.database import Base


class SystemAdmin(Base):
    __tablename__ = "system_admins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=True)
    telegram_chat_id = Column(String(100), nullable=True)
    whatsapp_phone = Column(String(100), nullable=True)
    notify_email = Column(Boolean, default=False, nullable=False)
    notify_telegram = Column(Boolean, default=True, nullable=False)
    notify_whatsapp = Column(Boolean, default=False, nullable=False)
    alert_types = Column(JSON, default=list, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "telegram_chat_id": self.telegram_chat_id,
            "whatsapp_phone": self.whatsapp_phone,
            "notify_email": self.notify_email,
            "notify_telegram": self.notify_telegram,
            "notify_whatsapp": self.notify_whatsapp,
            "alert_types": self.alert_types,
        }
