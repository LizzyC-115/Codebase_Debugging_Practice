"""
User Schemas

Request/response models for user operations.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema with common fields."""
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8, max_length=100)
    role: UserRole = UserRole.MEMBER


class UserUpdate(BaseModel):
    """Schema for updating a user. All fields optional."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """User response schema (excludes sensitive data)."""
    id: str
    tenant_id: str
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True  # Allows creating from ORM models


class UserListResponse(BaseModel):
    """Paginated list of users."""
    users: list[UserResponse]
    total: int
    page: int
    page_size: int
