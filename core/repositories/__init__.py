from .base import JpaRepository
from .tenant_repository import TenantRepository
from .channel_route_repository import ChannelRouteRepository
from .user_repository import UserRepository
from .conversation_repository import ConversationRepository
from .message_repository import MessageRepository
from .kb_repository import KBRepository
from .product_repository import ProductRepository
from .system_setting_repository import SystemSettingRepository

__all__ = [
    "JpaRepository",
    "TenantRepository",
    "ChannelRouteRepository",
    "UserRepository",
    "ConversationRepository",
    "MessageRepository",
    "KBRepository",
    "ProductRepository",
    "SystemSettingRepository",
]
