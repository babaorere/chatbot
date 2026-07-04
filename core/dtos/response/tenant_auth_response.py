from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TenantPortalUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    status: str
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantInviteResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    expires_at: datetime
    created_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None
    invite_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantSessionResponse(BaseModel):
    user: TenantPortalUserResponse


class TenantBootstrapResponse(BaseModel):
    user: TenantPortalUserResponse
    invite: TenantInviteResponse
