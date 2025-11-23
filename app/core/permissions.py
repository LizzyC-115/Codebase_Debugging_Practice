"""
Permission System (RBAC)

Implements role-based access control with a simple hierarchy.

DESIGN: We use a simple role-based system rather than full RBAC with
separate permissions. This covers 90% of use cases and is much simpler.
If you need fine-grained permissions, consider implementing:
- Permission table with specific permissions
- Role-Permission mapping table
- User-specific permission overrides

For now, three roles (admin, member, viewer) are sufficient.
"""
from typing import Optional
from fastapi import HTTPException, status
from app.models.user import User, UserRole


class PermissionDenied(HTTPException):
    """Custom exception for permission denied errors."""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


def require_role(user: User, required_role: UserRole) -> None:
    """
    Check if user has required role level.

    Raises PermissionDenied if user doesn't have sufficient permissions.

    Role hierarchy: ADMIN > MEMBER > VIEWER
    """
    if not user.has_permission(required_role):
        raise PermissionDenied(
            detail=f"This action requires {required_role.value} role or higher"
        )


def require_admin(user: User) -> None:
    """Shorthand for requiring admin role."""
    require_role(user, UserRole.ADMIN)


def require_member(user: User) -> None:
    """Shorthand for requiring member role or higher."""
    require_role(user, UserRole.MEMBER)


def can_modify_user(current_user: User, target_user: User) -> bool:
    """
    Check if current_user can modify target_user.

    Rules:
    - Admins can modify anyone in their tenant
    - Users can modify themselves
    - No cross-tenant modifications (enforced elsewhere)
    """
    if current_user.role == UserRole.ADMIN:
        return True
    return current_user.id == target_user.id


def can_delete_project(current_user: User, project_owner_id: str) -> bool:
    """
    Check if user can delete a project.

    Rules:
    - Admins can delete any project in their tenant
    - Project owners can delete their own projects
    - Members can delete their own projects
    - Viewers cannot delete anything
    """
    if current_user.role == UserRole.ADMIN:
        return True
    if current_user.role == UserRole.VIEWER:
        return False
    return current_user.id == project_owner_id


def can_modify_project(current_user: User, project_owner_id: Optional[str]) -> bool:
    """
    Check if user can modify a project.

    Similar to delete but slightly more permissive.
    Members can edit any project (collaborative editing).
    """
    if current_user.role == UserRole.VIEWER:
        return False
    return True


# NOTE: In a real system, you'd want more granular permissions like:
# - can_view_analytics
# - can_export_data
# - can_invite_users
# - can_manage_billing
# etc.
# This would typically be implemented with a permission decorator:
#
# @require_permission("can_export_data")
# async def export_data(...):
#     pass
#
# We're keeping it simple with roles for now.
