"""
Security Module

Handles password hashing, JWT token generation/validation.
Uses industry-standard libraries (passlib with bcrypt, python-jose).

SECURITY NOTES:
- Passwords are hashed with bcrypt (slow by design to prevent brute force)
- JWT tokens have expiration (prevent replay attacks)
- Token payload includes tenant_id for additional security layer
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import get_settings

settings = get_settings()

# Password hashing context
# Using bcrypt with default rounds (12) - good balance of security and performance
# TRADEOFF: Higher rounds = more secure but slower. 12 is industry standard.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    NOTE: This is intentionally slow (100ms+) to prevent brute force attacks.
    Don't call this in hot paths or tight loops.
    """
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Token payload includes:
    - sub: user_id
    - tenant_id: for additional verification
    - exp: expiration timestamp
    - iat: issued at timestamp

    SECURITY: We include tenant_id in the token to prevent a compromised
    token from being used across different tenants (defense in depth).
    """
    to_encode = data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })

    # Encode JWT
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT token.

    Returns the payload if valid, None if invalid/expired.

    SECURITY: This verifies signature and expiration automatically.
    Additional validation (tenant_id matching) happens in the dependency.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        # Token invalid, expired, or tampered with
        return None


def verify_token_tenant(token_payload: Dict[str, Any], expected_tenant_id: str) -> bool:
    """
    Verify that the token's tenant_id matches the expected tenant.

    This is an additional security layer to prevent cross-tenant token usage.
    Even if a token is valid, it should only work for its original tenant.

    PARANOID_MODE: You could also check if user still exists and is active,
    but that requires a DB query on every request (performance tradeoff).
    """
    token_tenant_id = token_payload.get("tenant_id")
    return token_tenant_id == expected_tenant_id
