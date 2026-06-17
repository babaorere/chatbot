from .health_controller import router as health_router
from .chat_controller import router as chat_router
from .tenant_controller import router as tenant_router
from .user_controller import router as user_router
from .session_controller import router as session_router
from .tenant_portal_controller import router as tenant_portal_router
from .admin_controller import router as admin_router
from .telegram_controller import router as telegram_router

__all__ = [
    "health_router",
    "chat_router",
    "tenant_router",
    "user_router",
    "session_router",
    "tenant_portal_router",
    "admin_router",
    "telegram_router",
]
