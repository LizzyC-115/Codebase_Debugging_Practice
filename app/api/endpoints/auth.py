"""
Authentication Endpoints

Handles user login and registration.
Registration creates users within a tenant context.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from app.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.auth import LoginRequest, Token, RegisterRequest
from app.schemas.user import UserResponse
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token
)
from app.core.exceptions import AuthenticationError
from app.config import get_settings
from app.utils.logging import log_security_event, get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=Token)
async def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticate user and return JWT token.

    Process:
    1. Load tenant by slug
    2. Find user in that tenant by email
    3. Verify password
    4. Generate JWT with user_id and tenant_id

    SECURITY: We scope login to a tenant to prevent email enumeration
    across tenants and ensure proper isolation from the start.
    """
    # Load tenant
    tenant = db.query(Tenant).filter(
        Tenant.slug == credentials.tenant_slug
    ).first()

    if not tenant:
        # SECURITY: Use generic error to prevent tenant enumeration
        log_security_event(
            "failed_login",
            {"reason": "tenant_not_found", "tenant_slug": credentials.tenant_slug},
            logger
        )
        raise AuthenticationError("Invalid credentials")

    if not tenant.is_active:
        log_security_event(
            "failed_login",
            {"reason": "tenant_inactive", "tenant_id": tenant.id},
            logger
        )
        raise AuthenticationError("Tenant account is inactive")

    # Find user in tenant
    user = db.query(User).filter(
        User.tenant_id == tenant.id,
        User.email == credentials.email
    ).first()

    if not user:
        # SECURITY: Generic error prevents user enumeration
        log_security_event(
            "failed_login",
            {"reason": "user_not_found", "email": credentials.email, "tenant_id": tenant.id},
            logger
        )
        raise AuthenticationError("Invalid credentials")

    # Verify password
    if not verify_password(credentials.password, user.hashed_password):
        log_security_event(
            "failed_login",
            {"reason": "invalid_password", "user_id": user.id, "tenant_id": tenant.id},
            logger
        )
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        log_security_event(
            "failed_login",
            {"reason": "user_inactive", "user_id": user.id},
            logger
        )
        raise AuthenticationError("User account is inactive")

    # Create access token
    token_data = {
        "sub": user.id,
        "tenant_id": tenant.id,
        "email": user.email
    }
    access_token = create_access_token(
        token_data,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Update last login timestamp
    # NOTE: Commented out to avoid DB write on every login for performance
    # Uncomment if you need accurate last_login tracking
    # user.last_login_at = datetime.utcnow()
    # db.commit()

    logger.info(f"Successful login: user={user.id}, tenant={tenant.id}")

    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    registration: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user in a tenant.

    NOTE: This is simplified. In production, you'd want:
    - Email verification flow
    - CAPTCHA to prevent bot registrations
    - Rate limiting on registrations
    - Tenant invitation codes or approval workflow

    CURRENT LIMITATION: Anyone can register to any tenant if they know
    the slug. This is fine for demo but not for production.
    """
    # Load tenant
    tenant = db.query(Tenant).filter(
        Tenant.slug == registration.tenant_slug
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant is not accepting new registrations"
        )

    # Check if user already exists in this tenant
    existing_user = db.query(User).filter(
        User.tenant_id == tenant.id,
        User.email == registration.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists in this tenant"
        )

    # Create new user
    hashed_password = get_password_hash(registration.password)

    new_user = User(
        tenant_id=tenant.id,
        email=registration.email,
        hashed_password=hashed_password,
        full_name=registration.full_name,
        role="member",  # Default role
        is_active=True,
        is_verified=False  # Would be True after email verification
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"New user registered: {new_user.id} in tenant {tenant.id}")

    return new_user


@router.post("/refresh", response_model=Token)
async def refresh_token(
    # In production, implement refresh tokens properly
    # For now, just a placeholder
):
    """
    Refresh access token.

    TODO: Implement proper refresh token mechanism with:
    - Separate refresh token storage
    - Refresh token rotation
    - Token family tracking for security
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Refresh token not implemented yet"
    )
