from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Column, String, DateTime, JSON, Text, func
from sqlalchemy.dialects.postgresql import UUID
from config.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="active")

    # Business profile fields
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    website = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    business_hours = Column(JSON, nullable=True, default=dict)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def get_instruction(self) -> str:
        return self.config.get("instruction", "")

    def get_model(self) -> str:
        return self.config.get(
            "model", "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
        )

    def get_api_key(self) -> str:
        return self.config.get("api_key", "")

    def get_products_legacy(self) -> list[dict[str, Any]]:
        return self.config.get("products", [])

    def get_business_hours_display(self) -> str:
        hours = self.business_hours or {}
        if not hours:
            return "Lunes a Sábado 10:00-22:00, Domingo 12:00-20:00"
        parts = []
        for day, schedule in hours.items():
            if isinstance(schedule, dict) and schedule.get("open"):
                parts.append(f"{day}: {schedule['open']}-{schedule['close']}")
        return ", ".join(parts) if parts else "Consultar horarios"
