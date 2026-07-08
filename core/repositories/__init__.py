from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "JpaRepository",
    "BusinessConfigRepository",
    "UserRepository",
    "ConversationRepository",
    "MessageRepository",
    "KBRepository",
    "ProductRepository",
    "SystemSettingRepository",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "JpaRepository": ("repositories.base", "JpaRepository"),
    "BusinessConfigRepository": (
        "repositories.business_config_repository",
        "BusinessConfigRepository",
    ),
    "UserRepository": ("repositories.user_repository", "UserRepository"),
    "ConversationRepository": (
        "repositories.conversation_repository",
        "ConversationRepository",
    ),
    "MessageRepository": ("repositories.message_repository", "MessageRepository"),
    "KBRepository": ("repositories.kb_repository", "KBRepository"),
    "ProductRepository": ("repositories.product_repository", "ProductRepository"),
    "SystemSettingRepository": (
        "repositories.system_setting_repository",
        "SystemSettingRepository",
    ),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_IMPORTS[name]
    except KeyError as exc:
        raise AttributeError(
            f"module 'repositories' has no attribute {name!r}"
        ) from exc

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
