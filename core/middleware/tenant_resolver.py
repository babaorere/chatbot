from __future__ import annotations


from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from exceptions.tenant_exceptions import TenantResolutionError


class TenantResolverMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exclude_paths: list[str] | None = None) -> None:
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        tenant_header = request.headers.get("X-Tenant-ID")
        platform = request.headers.get("X-Platform")
        channel_identifier = request.headers.get("X-Channel-Identifier")

        if not tenant_header and not (platform and channel_identifier):
            raise TenantResolutionError(
                "Missing X-Tenant-ID or channel mapping headers"
            )

        request.state.tenant_resolution = {
            "tenant_id_header": tenant_header,
            "platform": platform,
            "channel_identifier": channel_identifier,
        }

        return await call_next(request)
