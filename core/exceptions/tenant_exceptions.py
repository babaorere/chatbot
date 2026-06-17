from __future__ import annotations

import uuid


class TenantNotFoundError(Exception):
    def __init__(self, tenant_id: uuid.UUID | str | None = None) -> None:
        self.tenant_id = tenant_id
        if tenant_id:
            super().__init__(f"Tenant not found: {tenant_id}")
        else:
            super().__init__("Tenant not found")


class TenantInactiveError(Exception):
    def __init__(self, tenant_id: uuid.UUID | str) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant is inactive: {tenant_id}")


class ChannelRouteNotFoundError(Exception):
    def __init__(self, platform: str, channel_identifier: str) -> None:
        self.platform = platform
        self.channel_identifier = channel_identifier
        super().__init__(
            f"No channel route found for platform={platform}, channel={channel_identifier}"
        )


class TenantResolutionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Tenant resolution failed: {reason}")
