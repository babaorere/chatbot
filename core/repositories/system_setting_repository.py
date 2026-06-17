from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from models.system_setting import SystemSetting
from repositories.base import JpaRepository

logger = logging.getLogger(__name__)


class SystemSettingRepository(JpaRepository[SystemSetting]):
    def __init__(self, db: Session) -> None:
        super().__init__(SystemSetting, db)

    def get_value(self, key: str) -> Any | None:
        try:
            setting = (
                self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
            )
            return setting.value if setting else None
        except Exception as e:
            logger.error(
                "SystemSettingRepository.get_value failed [key=%s]: %s", key, e
            )
            raise

    def set_value(
        self, key: str, value: Any, description: str | None = None
    ) -> SystemSetting:
        try:
            setting = (
                self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
            )
            if setting:
                setting.value = value
                if description is not None:
                    setting.description = description
            else:
                setting = SystemSetting(key=key, value=value, description=description)
                self.db.add(setting)
            self.db.flush()
            self.db.refresh(setting)
            return setting
        except Exception as e:
            logger.error(
                "SystemSettingRepository.set_value failed [key=%s]: %s", key, e
            )
            raise

    def get_all_settings(self) -> dict[str, Any]:
        try:
            settings = self.db.query(SystemSetting).all()
            return {s.key: s.value for s in settings}
        except Exception as e:
            logger.error("SystemSettingRepository.get_all_settings failed: %s", e)
            raise
