from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TenantInviteCreateRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        description="Nombre sugerido para el usuario invitado",
    )
    role: str = Field(
        default="manager",
        pattern="^(owner|manager|staff)$",
        description="Rol inicial del usuario tenant",
    )
    created_by_admin_id: int | None = Field(
        default=None,
        ge=1,
        description="Administrador del sistema que emitió la invitación",
    )


class TenantInviteClaimRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    full_name: str = Field(..., min_length=2, max_length=120)
    password: str = Field(..., min_length=12, max_length=256)


class TenantLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1, max_length=256)


class TenantUserDisableRequest(BaseModel):
    disabled: bool = True


class TenantPasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=256)


class TenantAuthContext(BaseModel):
    user_agent: str | None = None
    ip_address: str | None = None

    model_config = ConfigDict(extra="ignore")
