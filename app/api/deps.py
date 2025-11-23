"""
API Dependencies

Reusable FastAPI dependencies for authentication and authorization.
These are used across all API endpoints to ensure consistent security.

PATTERN: FastAPI's dependency injection system is powerful and clean.
Dependencies can be composed and reused easily.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.tenant import Tenant
from app.core.security import decode_access_token
from app.core.exceptions import AuthenticationError, TenantIsolationError
import logging

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer()


def get_current_tenant(request: Request) -> Tenant:
    """
    Get current tenant from request state.

    This is set by TenantMiddleware and should always be present
    for authenticated routes.

    CRITICAL: This is a key part of tenant isolation.
    """
    tenant = getattr(request.state, "tenant", None)
    if not tenant:
        logger.error("No tenant in request state - middleware may have failed")
        raise TenantIsolationError("Tenant context not available")
    return tenant


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant)
) -> User:
    """
    Get current authenticated user.

    This dependency:
    1. Validates JWT token
    2. Loads user from database
    3. Verifies user belongs to current tenant (CRITICAL)
    4. Checks user is active

    SECURITY: Multiple layers of validation prevent token reuse
    across tenants and ensure proper isolation.
    """
    token = credentials.credentials

    # Decode JWT token
    payload = decode_access_token(token)
    if not payload:
        raise AuthenticationError("Invalid or expired token")

    user_id = payload.get("sub")
    token_tenant_id = payload.get("tenant_id")

    if not user_id:
        raise AuthenticationError("Invalid token payload")

    # CRITICAL SECURITY CHECK: Verify token's tenant matches request tenant
    # This prevents a valid token from one tenant being used for another
    if token_tenant_id != tenant.id:
        logger.error(
            f"Tenant mismatch: token={token_tenant_id}, request={tenant.id}",
            extra={"user_id": user_id, "token_tenant": token_tenant_id, "request_tenant": tenant.id}
        )
        raise TenantIsolationError("Token tenant mismatch")

    # Load user from database
    # PERFORMANCE NOTE: This is a DB query on every authenticated request
    # High-scale systems might cache user data in Redis with short TTL
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant.id  # Double-check tenant isolation
    ).first()

    if not user:
        logger.warning(f"User not found: {user_id} in tenant {tenant.id}")
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user.

    Additional check on top of get_current_user.
    Kept separate for flexibility.
    """
    if not current_user.is_active:
        raise AuthenticationError("Inactive user")
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require admin role.

    Use this dependency for admin-only endpoints.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


async def require_member(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require member role or higher.

    Members and admins can access, viewers cannot.
    """
    if not current_user.has_permission(UserRole.MEMBER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Member privileges required"
        )
    return current_user


# Optional authentication dependency
# Use this when endpoint supports both authenticated and anonymous access
async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise.

    Use for endpoints that behave differently for authenticated users
    but don't require authentication.
    """
    try:
        # Try to extract bearer token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.replace("Bearer ", "")
        payload = decode_access_token(token)
        if not payload:
            return None

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        if not user_id or not tenant_id:
            return None

        user = db.query(User).filter(
            User.id == user_id,
            User.tenant_id == tenant_id
        ).first()

        return user if user and user.is_active else None

    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
        return None
