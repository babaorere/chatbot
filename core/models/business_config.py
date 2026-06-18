from __future__ import annotations

import uuid

from sqlalchemy import Column, String, DateTime, JSON, Text, func
from sqlalchemy.dialects.postgresql import UUID
from config.database import Base


class BusinessConfig(Base):
    __tablename__ = "business_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    website = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    business_hours = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def get_business_hours_display(self) -> str:
        hours = self.business_hours or {}
        if not hours:
            return "Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00"
        parts = []
        for day, schedule in hours.items():
            if isinstance(schedule, dict) and schedule.get("open"):
                parts.append(f"{day}: {schedule['open']}-{schedule['close']}")
        return ", ".join(parts) if parts else "Consultar horarios"
