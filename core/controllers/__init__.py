from .health_controller import router as health_router
from .chat_controller import router as chat_router
from .user_controller import router as user_router
from .session_controller import router as session_router
from .business_config_controller import router as business_config_router
from .admin_controller import router as admin_router
from .telegram_controller import router as telegram_router
from .order_controller import router as order_router

__all__ = [
    "health_router",
    "chat_router",
    "user_router",
    "session_router",
    "business_config_router",
    "admin_router",
    "telegram_router",
    "order_router",
]
