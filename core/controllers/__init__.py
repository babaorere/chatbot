from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "health_router",
    "chat_router",
    "user_router",
    "session_router",
    "business_config_router",
    "business_router",
    "admin_router",
    "tenant_access_admin_router",
    "tenant_auth_router",
    "telegram_router",
    "order_router",
    "category_router",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "health_router": ("controllers.health_controller", "router"),
    "chat_router": ("controllers.chat_controller", "router"),
    "user_router": ("controllers.user_controller", "router"),
    "session_router": ("controllers.session_controller", "router"),
    "business_config_router": (
        "controllers.business_config_controller",
        "router",
    ),
    "business_router": ("controllers.business_controller", "router"),
    "admin_router": ("controllers.admin_controller", "router"),
    "tenant_access_admin_router": (
        "controllers.tenant_access_admin_controller",
        "router",
    ),
    "tenant_auth_router": ("controllers.tenant_auth_controller", "router"),
    "telegram_router": ("controllers.telegram_controller", "router"),
    "order_router": ("controllers.order_controller", "router"),
    "category_router": ("controllers.category_controller", "router"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_IMPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'controllers' has no attribute {name!r}") from exc

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
