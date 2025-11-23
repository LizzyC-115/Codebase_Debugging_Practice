"""
User Management Endpoints

CRUD operations for users within a tenant.
All operations are scoped to the current tenant (enforced by middleware).

RBAC:
- List users: All authenticated users
- Get user: All authenticated users (own tenant only)
- Create user: Admin only
- Update user: Admin or self
- Delete user: Admin only
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User, UserRole
from app.models.tenant import Tenant
from app.schemas.user import (
    UserResponse,
    UserCreate,
    UserUpdate,
    UserListResponse
)
from app.api.deps import (
    get_current_user,
    get_current_tenant,
    require_admin
)
from app.core.security import get_password_hash
from app.core.permissions import require_role, can_modify_user
from app.core.exceptions import UserNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: UserRole = Query(None),
    is_active: bool = Query(None),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    List users in current tenant.

    Supports filtering by role and active status.
    Paginated for performance.

    TENANT_ISOLATION: Automatically filtered by current tenant.
    """
    # Build query with tenant filter (CRITICAL for isolation)
    query = db.query(User).filter(User.tenant_id == tenant.id)

    # Apply optional filters
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    users = query.offset(offset).limit(page_size).all()

    logger.debug(f"Listed {len(users)} users for tenant {tenant.id}")

    return UserListResponse(
        users=users,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Get user by ID.

    TENANT_ISOLATION: Can only access users in same tenant.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant.id  # CRITICAL: Tenant isolation
    ).first()

    if not user:
        raise UserNotFoundError(user_id)

    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin),  # Admin only
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Create a new user in current tenant.

    Requires admin role.

    BUSINESS LOGIC: In production, you might want to:
    - Send invitation email instead of directly creating
    - Enforce user limits based on subscription tier
    - Require email verification before activation
    """
    # Check if user already exists in tenant
    existing_user = db.query(User).filter(
        User.tenant_id == tenant.id,
        User.email == user_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Hash password
    hashed_password = get_password_hash(user_data.password)

    # Create user
    new_user = User(
        tenant_id=tenant.id,  # CRITICAL: Set tenant_id
        email=user_data.email,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"User created: {new_user.id} by {current_user.id}")

    return new_user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Update user information.

    Permissions:
    - Admin: Can update any user in tenant
    - User: Can update themselves

    SECURITY: Role changes require admin privileges.
    """
    # Load target user with tenant isolation
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant.id  # CRITICAL
    ).first()

    if not user:
        raise UserNotFoundError(user_id)

    # Check permissions
    if not can_modify_user(current_user, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this user"
        )

    # Role changes require admin
    if user_data.role and user_data.role != user.role:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change user roles"
            )

    # Apply updates
    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    logger.info(f"User updated: {user.id} by {current_user.id}")

    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_admin),  # Admin only
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db)
):
    """
    Delete user from tenant.

    Requires admin role.

    CAUTION: This is a hard delete. Consider soft delete for audit trail.
    In production, you'd want to:
    - Prevent deleting the last admin
    - Reassign or delete user's resources
    - Send notification to user
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == tenant.id  # CRITICAL
    ).first()

    if not user:
        raise UserNotFoundError(user_id)

    # Prevent self-deletion
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    # TODO: Check if last admin and prevent deletion

    db.delete(user)
    db.commit()

    logger.info(f"User deleted: {user_id} by {current_user.id}")

    return None
