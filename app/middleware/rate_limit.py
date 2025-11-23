"""
Rate Limiting Middleware

Per-tenant rate limiting using Redis.

ARCHITECTURE: We use token bucket algorithm with Redis.
Each tenant has their own rate limit bucket.

ALTERNATIVE APPROACHES:
- Fixed window: Simple but has burst issues at window boundaries
- Sliding window: More accurate but more complex
- Token bucket: Good balance (what we use)

PRODUCTION NOTES:
- Redis is single point of failure (use Redis Cluster/Sentinel)
- Rate limits should be configurable per tenant (subscription tier)
- Need monitoring/alerting for rate limit violations
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from typing import Optional
import redis
import time
import logging
from app.config import get_settings
from app.core.exceptions import RateLimitExceeded

logger = logging.getLogger(__name__)
settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token bucket rate limiter per tenant.

    Each tenant gets their own rate limit based on subscription tier.
    Uses Redis for distributed rate limiting.
    """

    def __init__(self, app):
        super().__init__(app)

        # Initialize Redis connection
        # FIXME: This should use connection pooling for production
        try:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Redis connection established for rate limiting")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.error(f"Redis connection failed: {e}")
            self.redis_available = False
            # FALLBACK: Disable rate limiting if Redis is down
            # In production, you might want to fail closed instead

        self.excluded_paths = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
        ]

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting per tenant."""

        # Skip rate limiting for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)

        # Skip if Redis not available (graceful degradation)
        # TRADEOFF: We choose availability over strict rate limiting
        # Alternative: Fail closed and reject requests
        if not self.redis_available:
            logger.warning("Rate limiting disabled - Redis unavailable")
            return await call_next(request)

        # Get tenant from request state (set by TenantMiddleware)
        tenant = getattr(request.state, "tenant", None)
        if not tenant:
            # No tenant context, skip rate limiting
            return await call_next(request)

        # Check rate limit
        allowed, retry_after = self._check_rate_limit(tenant)

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for tenant {tenant.slug}",
                extra={"tenant_id": tenant.id}
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )

        response = await call_next(request)
        return response

    def _check_rate_limit(self, tenant) -> tuple[bool, int]:
        """
        Check if request is allowed under rate limit.

        Returns: (allowed: bool, retry_after: int)

        Uses token bucket algorithm:
        - Bucket holds max tokens (burst capacity)
        - Tokens added at fixed rate
        - Each request consumes one token
        """
        # Get tenant-specific rate limits (or use defaults)
        rate_limit = tenant.rate_limit_per_minute or settings.RATE_LIMIT_PER_MINUTE
        burst = tenant.rate_limit_burst or settings.RATE_LIMIT_BURST

        # Redis keys for this tenant's bucket
        key = f"rate_limit:{tenant.id}"
        key_timestamp = f"{key}:timestamp"

        try:
            # Get current tokens and last update time
            current_tokens = self.redis_client.get(key)
            last_update = self.redis_client.get(key_timestamp)

            now = time.time()

            if current_tokens is None:
                # First request - initialize bucket
                current_tokens = burst - 1  # Consume one token
                self.redis_client.setex(key, 60, current_tokens)
                self.redis_client.setex(key_timestamp, 60, now)
                return True, 0

            current_tokens = float(current_tokens)
            last_update = float(last_update) if last_update else now

            # Calculate tokens to add based on elapsed time
            elapsed = now - last_update
            tokens_to_add = elapsed * (rate_limit / 60.0)  # Convert per-minute to per-second
            new_tokens = min(burst, current_tokens + tokens_to_add)

            if new_tokens >= 1:
                # Allow request and consume token
                new_tokens -= 1
                self.redis_client.setex(key, 60, new_tokens)
                self.redis_client.setex(key_timestamp, 60, now)
                return True, 0
            else:
                # Rate limit exceeded - calculate retry time
                tokens_needed = 1 - new_tokens
                retry_after = int((tokens_needed / (rate_limit / 60.0)) + 1)
                return False, retry_after

        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiting: {e}")
            # Graceful degradation - allow request if Redis fails
            return True, 0

    def _get_client_identifier(self, request: Request) -> str:
        """
        Get identifier for rate limiting.

        Uses tenant_id as primary identifier.
        Could be extended to include user_id for per-user limits.
        """
        tenant_id = getattr(request.state, "tenant_id", "unknown")
        return tenant_id
