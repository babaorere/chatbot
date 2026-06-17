from __future__ import annotations

from sqlalchemy import Column, String, DateTime, Text, JSON, func
from config.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def get_value(self):
        return self.value

    def get_string(self) -> str:
        if isinstance(self.value, str):
            return self.value
        return str(self.value)

    def get_int(self) -> int:
        if isinstance(self.value, int):
            return self.value
        if isinstance(self.value, str):
            return int(self.value)
        return int(str(self.value))

    def get_bool(self) -> bool:
        if isinstance(self.value, bool):
            return self.value
        if isinstance(self.value, str):
            return self.value.lower() in ("true", "1", "yes")
        return bool(self.value)

    def get_list(self) -> list:
        if isinstance(self.value, list):
            return self.value
        return []

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
