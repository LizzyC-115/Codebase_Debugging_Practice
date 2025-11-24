"""
Resource Model

Resources are sub-entities belonging to projects, demonstrating
a two-level tenant isolation hierarchy:
    Tenant -> Project -> Resource

This pattern is common when you have nested resources that need
to maintain the tenant isolation chain.
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, Integer, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # CRITICAL: Tenant foreign key for isolation
    # We duplicate tenant_id here even though it's implicit through project_id
    # REASON: Query performance - we can filter by tenant_id without joining projects table
    # TRADEOFF: Data duplication vs query performance (we chose performance)
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Parent project
    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Resource data
    name = Column(String(255), nullable=False)
    resource_type = Column(
        String(50),
        nullable=False,
        index=True
    )  # document, image, file, etc.

    # File/content information
    content = Column(Text, nullable=True)  # For text-based resources
    file_url = Column(String(512), nullable=True)  # S3/storage URL for files
    file_size = Column(Integer, nullable=True)  # Size in bytes
    mime_type = Column(String(100), nullable=True)

    # Metadata stored as JSON
    # NOTE: Using JSON column is convenient but makes querying harder
    # If you need to query this data frequently, normalize it to proper columns
    resource_metadata = Column(JSON, nullable=True, default=dict)

    # Versioning info
    # FUTURE: Implement proper versioning with a separate resource_versions table
    version = Column(Integer, default=1, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="resources")
    project = relationship("Project", back_populates="resources")

    # Indexes for common queries
    __table_args__ = (
        # Most common: resources in a project
        Index('idx_resource_project', 'project_id', 'created_at'),
        # Resources by type within tenant
        Index('idx_resource_tenant_type', 'tenant_id', 'resource_type'),
        # Direct tenant lookup for isolation enforcement
        Index('idx_resource_tenant', 'tenant_id'),
    )

    def __repr__(self):
        return f"<Resource {self.name} type={self.resource_type} (tenant={self.tenant_id})>"

    @property
    def file_size_mb(self):
        """Helper property for display purposes."""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0
