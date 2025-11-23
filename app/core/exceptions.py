"""
Custom Exceptions

Centralized exception definitions for better error handling.
FastAPI automatically converts these to appropriate HTTP responses.
"""
from fastapi import HTTPException, status


class TenantNotFoundError(HTTPException):
    """Raised when tenant cannot be found."""

    def __init__(self, tenant_identifier: str = ""):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant not found: {tenant_identifier}" if tenant_identifier else "Tenant not found"
        )


class UserNotFoundError(HTTPException):
    """Raised when user cannot be found."""

    def __init__(self, user_id: str = ""):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}" if user_id else "User not found"
        )


class ProjectNotFoundError(HTTPException):
    """Raised when project cannot be found."""

    def __init__(self, project_id: str = ""):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}" if project_id else "Project not found"
        )


class ResourceNotFoundError(HTTPException):
    """Raised when resource cannot be found."""

    def __init__(self, resource_id: str = ""):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}" if resource_id else "Resource not found"
        )


class AuthenticationError(HTTPException):
    """Raised when authentication fails."""

    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class TenantIsolationError(HTTPException):
    """
    Raised when a tenant isolation violation is detected.

    This is a CRITICAL security error and should be logged/alerted on.
    """

    def __init__(self, detail: str = "Tenant isolation violation"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


class RateLimitExceeded(HTTPException):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(retry_after)}
        )


class InvalidInputError(HTTPException):
    """Raised when input validation fails."""

    def __init__(self, detail: str = "Invalid input"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


# FUTURE: Add more specific exceptions as needed:
# - DuplicateResourceError
# - QuotaExceededError
# - MaintenanceModeError
# etc.
