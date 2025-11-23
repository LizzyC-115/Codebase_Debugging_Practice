"""
Tenant Model

The tenant is the primary isolation boundary in our multi-tenant architecture.
Each tenant represents a separate customer/organization with complete data isolation.

ARCHITECTURAL DECISION: We use shared database, separate schemas approach.
Alternative approaches considered:
- Separate databases per tenant (better isolation, harder to manage at scale)
- Shared database, shared schema with tenant_id filter (what we chose - balance of isolation and manageability)
- Separate databases with connection pooling (too complex for our scale)
"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid


class Tenant(Base):
    __tablename__ = "tenants"

    # Using UUID for tenant IDs to avoid enumeration attacks
    # and make IDs globally unique across systems
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Tenant identification
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)

    # Subdomain for tenant routing (e.g., acme.saas.com)
    # TODO: Support custom domains in the future
    subdomain = Column(String(63), unique=True, nullable=False, index=True)

    # Status and subscription info
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Subscription tier - affects rate limits and features
    # HACK: This should really be in a separate subscriptions table
    # but keeping it simple for now. Will refactor when we add
    # proper billing integration.
    subscription_tier = Column(
        String(20),
        default="free",
        nullable=False
    )  # free, basic, premium, enterprise

    # Rate limiting settings per tenant
    # These override the global defaults
    rate_limit_per_minute = Column(Integer, nullable=True)  # NULL = use default
    rate_limit_burst = Column(Integer, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Contact and billing info
    admin_email = Column(String(255), nullable=False)
    billing_email = Column(String(255), nullable=True)

    # Feature flags stored as JSON would be better, but using simple booleans for now
    # TECHNICAL_DEBT: Migrate to a proper feature flag system
    feature_advanced_analytics = Column(Boolean, default=False)
    feature_api_access = Column(Boolean, default=True)
    feature_custom_branding = Column(Boolean, default=False)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="tenant", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="tenant", cascade="all, delete-orphan")

    # Composite index for common queries
    __table_args__ = (
        Index('idx_tenant_active_subdomain', 'is_active', 'subdomain'),
        Index('idx_tenant_slug', 'slug'),
    )

    def __repr__(self):
        return f"<Tenant {self.slug}>"

    @property
    def is_premium(self):
        """Helper to check if tenant has premium features."""
        return self.subscription_tier in ['premium', 'enterprise']
