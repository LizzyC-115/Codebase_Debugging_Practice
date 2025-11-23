"""
Project Schemas

Request/response models for project operations.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProjectBase(BaseModel):
    """Base project schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_public: bool = False


class ProjectCreate(ProjectBase):
    """Schema for creating a project."""
    pass


class ProjectUpdate(BaseModel):
    """Schema for updating a project. All fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|archived|completed)$")
    is_public: Optional[bool] = None


class ProjectResponse(ProjectBase):
    """Project response schema."""
    id: str
    tenant_id: str
    owner_id: Optional[str]
    status: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    view_count: int
    last_accessed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""
    projects: list[ProjectResponse]
    total: int
    page: int
    page_size: int
