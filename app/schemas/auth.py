"""
Authentication Schemas

Request/response models for authentication endpoints.
"""
from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Decoded token data."""
    user_id: str
    tenant_id: str


class LoginRequest(BaseModel):
    """Login request body."""
    email: EmailStr
    password: str = Field(..., min_length=8)

    # Include tenant identifier in login
    # This could be subdomain, slug, or explicit tenant_id
    tenant_slug: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=255)
    tenant_slug: str = Field(..., min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepassword123",
                "full_name": "John Doe",
                "tenant_slug": "acme-corp"
            }
        }
