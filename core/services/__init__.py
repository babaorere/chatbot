from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "BusinessConfigService",
    "UserService",
    "ConversationService",
    "KBService",
    "ProductService",
    "RAGPolicyResult",
    "RAGPolicyService",
    "RAGContextBuilder",
    "RedisSessionService",
    "create_session_service",
    "AgentFactory",
    "transactional",
    "send_telegram_message",
    "CartService",
    "OrderService",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "CartService": ("services.cart_service", "CartService"),
    "OrderService": ("services.order_service", "OrderService"),
    "BusinessConfigService": (
        "services.business_config_service",
        "BusinessConfigService",
    ),
    "UserService": ("services.user_service", "UserService"),
    "ConversationService": (
        "services.conversation_service",
        "ConversationService",
    ),
    "KBService": ("services.kb_service", "KBService"),
    "ProductService": ("services.product_service", "ProductService"),
    "RAGPolicyResult": ("services.rag_policy", "RAGPolicyResult"),
    "RAGPolicyService": ("services.rag_policy", "RAGPolicyService"),
    "RAGContextBuilder": (
        "services.rag_context_builder",
        "RAGContextBuilder",
    ),
    "RedisSessionService": (
        "services.redis_session_service",
        "RedisSessionService",
    ),
    "create_session_service": (
        "services.session_service_factory",
        "create_session_service",
    ),
    "AgentFactory": ("services.agent_factory", "AgentFactory"),
    "transactional": ("services.transactional", "transactional"),
    "send_telegram_message": ("services.telegram_service", "send_telegram_message"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_IMPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'services' has no attribute {name!r}") from exc

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
