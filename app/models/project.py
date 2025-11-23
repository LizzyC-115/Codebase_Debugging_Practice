"""
Project Model

Projects are tenant-scoped resources that demonstrate basic CRUD operations
in a multi-tenant context. They belong to a tenant and have an owner.

This is a typical resource pattern you'd replicate for other entities
like "workspaces", "teams", "documents", etc.
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # CRITICAL: Tenant foreign key for isolation
    # This ensures projects are scoped to a tenant
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Owner relationship
    # NOTE: Owner must be in the same tenant (enforced at application level)
    owner_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # Nullable to handle user deletion gracefully
        index=True
    )

    # Project data
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        String(20),
        default="active",
        nullable=False,
        index=True
    )  # active, archived, completed

    # Settings and configuration
    is_public = Column(Boolean, default=False, nullable=False)

    # Soft delete pattern - common in SaaS to allow recovery
    # TRADEOFF: Adds complexity but users expect "undelete" functionality
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Metadata for analytics/tracking
    view_count = Column(Integer, default=0, nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="projects")
    owner = relationship("User", back_populates="projects")
    resources = relationship("Resource", back_populates="project", cascade="all, delete-orphan")

    # Indexes for common queries
    __table_args__ = (
        # Most common query: active projects for a tenant
        Index('idx_project_tenant_status', 'tenant_id', 'is_deleted', 'status'),
        # Projects by owner
        Index('idx_project_owner', 'owner_id', 'is_deleted'),
        # Search by name within tenant
        Index('idx_project_tenant_name', 'tenant_id', 'name'),
    )

    def __repr__(self):
        return f"<Project {self.name} (tenant={self.tenant_id})>"

    def soft_delete(self):
        """
        Soft delete pattern implementation.

        In production, you might want to cascade this to related resources
        or move data to an archive table.
        """
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
