"""
Resource Schemas

Request/response models for resource operations.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class ResourceBase(BaseModel):
    """Base resource schema."""
    name: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(..., min_length=1, max_length=50)
    content: Optional[str] = None
    file_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ResourceCreate(ResourceBase):
    """Schema for creating a resource."""
    project_id: str


class ResourceUpdate(BaseModel):
    """Schema for updating a resource. All fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = None
    file_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ResourceResponse(ResourceBase):
    """Resource response schema."""
    id: str
    tenant_id: str
    project_id: str
    file_size: Optional[int]
    mime_type: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResourceListResponse(BaseModel):
    """Paginated list of resources."""
    resources: list[ResourceResponse]
    total: int
    page: int
    page_size: int
