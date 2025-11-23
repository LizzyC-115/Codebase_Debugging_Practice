"""
Tenant Middleware

Extracts tenant context from requests and makes it available throughout
the request lifecycle. This is CRITICAL for multi-tenant isolation.

ARCHITECTURE: We use subdomain-based tenant routing:
- acme.saas.com -> tenant with subdomain "acme"
- contoso.saas.com -> tenant with subdomain "contoso"

ALTERNATIVE APPROACHES:
1. Header-based: X-Tenant-ID header (what we also support as fallback)
2. Path-based: /tenants/{tenant_id}/... (less clean URLs)
3. Separate domains per tenant (complex DNS management)

We chose subdomain + header fallback for flexibility.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.database import SessionLocal
from app.models.tenant import Tenant
from app.core.exceptions import TenantNotFoundError

logger = logging.getLogger(__name__)


class TenantContext:
    """
    Thread-local tenant context.

    Stores the current tenant for the request.
    This is accessible via request.state.tenant in route handlers.
    """

    def __init__(self, tenant: Tenant):
        self.tenant = tenant

    @property
    def tenant_id(self) -> str:
        return self.tenant.id

    @property
    def is_active(self) -> bool:
        return self.tenant.is_active


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and validate tenant from request.

    This runs on EVERY request and adds tenant context to request.state.
    Performance is critical here.

    SECURITY: This is the first line of defense for tenant isolation.
    If this fails, entire isolation model breaks down.
    """

    def __init__(self, app):
        super().__init__(app)
        self.excluded_paths = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
        ]

    async def dispatch(self, request: Request, call_next):
        """Process each request and inject tenant context."""

        # Skip tenant resolution for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)

        # Extract tenant identifier from request
        tenant_identifier = self._extract_tenant_identifier(request)

        if not tenant_identifier:
            logger.warning(f"No tenant identifier in request: {request.url}")
            return JSONResponse(
                status_code=400,
                content={"detail": "Tenant identifier required (subdomain or X-Tenant-Slug header)"}
            )

        # Load tenant from database
        # NOTE: This is a DB query on every request. In high-scale systems,
        # you'd want to cache this in Redis with TTL.
        db = SessionLocal()
        try:
            tenant = self._load_tenant(db, tenant_identifier)

            if not tenant:
                logger.warning(f"Tenant not found: {tenant_identifier}")
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"Tenant not found: {tenant_identifier}"}
                )

            if not tenant.is_active:
                logger.warning(f"Inactive tenant attempted access: {tenant_identifier}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Tenant account is inactive"}
                )

            # Inject tenant context into request state
            request.state.tenant = tenant
            request.state.tenant_id = tenant.id

            # Log tenant access for audit trail
            logger.debug(f"Request for tenant: {tenant.slug} ({tenant.id})")

            response = await call_next(request)
            return response

        finally:
            db.close()

    def _extract_tenant_identifier(self, request: Request) -> Optional[str]:
        """
        Extract tenant identifier from request.

        Priority:
        1. X-Tenant-Slug header (for API clients)
        2. Subdomain extraction from Host header
        3. X-Tenant-ID header (legacy, less secure)
        """
        # Try header first (most explicit)
        tenant_slug = request.headers.get("X-Tenant-Slug")
        if tenant_slug:
            return tenant_slug

        # Try subdomain extraction
        host = request.headers.get("Host", "")
        if host:
            # Extract subdomain: "acme.saas.com" -> "acme"
            parts = host.split(".")
            if len(parts) >= 3:  # subdomain.domain.tld
                subdomain = parts[0]
                # Exclude common non-tenant subdomains
                if subdomain not in ["www", "api", "app"]:
                    return subdomain

        # Fallback to tenant ID header (less preferred)
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            logger.debug("Using X-Tenant-ID header (legacy)")
            return tenant_id

        return None

    def _load_tenant(self, db: Session, identifier: str) -> Optional[Tenant]:
        """
        Load tenant from database by identifier.

        Tries slug, subdomain, then ID.

        PERFORMANCE: This hits DB on every request. Consider caching.
        """
        # Try slug first (most common)
        tenant = db.query(Tenant).filter(Tenant.slug == identifier).first()
        if tenant:
            return tenant

        # Try subdomain
        tenant = db.query(Tenant).filter(Tenant.subdomain == identifier).first()
        if tenant:
            return tenant

        # Try ID as last resort
        tenant = db.query(Tenant).filter(Tenant.id == identifier).first()
        return tenant
