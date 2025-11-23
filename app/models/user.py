"""
User Model

Users belong to a tenant and have role-based access control.

IMPORTANT: tenant_id is the critical field for data isolation.
Every query MUST filter by tenant_id to prevent cross-tenant data leaks.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid
import enum


class UserRole(str, enum.Enum):
    """
    User roles for RBAC.

    ADMIN: Full access to tenant resources, can manage users
    MEMBER: Standard access, can create/edit own resources
    VIEWER: Read-only access to tenant resources

    NOTE: We use a simple role enum here. In a more complex system,
    you'd want a proper RBAC system with permissions and roles tables.
    This is a known limitation but works for 80% of use cases.
    """
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # CRITICAL: Tenant foreign key for data isolation
    # Every user belongs to exactly one tenant
    # ON DELETE CASCADE ensures orphaned users are cleaned up
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # User credentials and profile
    email = Column(String(255), nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)

    # Role-based access control
    role = Column(
        SQLEnum(UserRole),
        default=UserRole.MEMBER,
        nullable=False,
        index=True
    )

    # Account status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # Password reset tracking
    # SECURITY: These should be in a separate table for better security
    # but keeping simple for now
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    projects = relationship("Project", back_populates="owner")

    # Composite indexes for common query patterns
    __table_args__ = (
        # CRITICAL: Unique constraint scoped to tenant
        # This allows same email across different tenants
        Index('idx_user_tenant_email', 'tenant_id', 'email', unique=True),
        # Common query: active users in a tenant
        Index('idx_user_tenant_active', 'tenant_id', 'is_active'),
        # Common query: users by role in tenant
        Index('idx_user_tenant_role', 'tenant_id', 'role'),
    )

    def __repr__(self):
        return f"<User {self.email} (tenant={self.tenant_id})>"

    def has_permission(self, required_role: UserRole) -> bool:
        """
        Check if user has required permission level.

        Simple hierarchy: ADMIN > MEMBER > VIEWER
        This is a simplified permission model. Production systems
        usually need more granular permissions.
        """
        role_hierarchy = {
            UserRole.VIEWER: 1,
            UserRole.MEMBER: 2,
            UserRole.ADMIN: 3,
        }
        return role_hierarchy[self.role] >= role_hierarchy[required_role]
