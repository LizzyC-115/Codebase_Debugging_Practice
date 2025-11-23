"""
Main FastAPI Application

Entry point for the multi-tenant SaaS platform.
Configures middleware, routes, error handlers, and startup/shutdown events.

PRODUCTION CHECKLIST:
- [ ] Enable HTTPS only
- [ ] Configure CORS properly
- [ ] Set up proper logging/monitoring
- [ ] Configure database connection pooling
- [ ] Set up health checks and metrics
- [ ] Enable request ID tracking
- [ ] Configure rate limiting per tenant tier
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import logging
import time
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import engine, Base, init_db
from app.middleware.tenant import TenantMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.utils.logging import setup_logging, get_logger
from app.core.exceptions import (
    TenantNotFoundError,
    AuthenticationError,
    TenantIsolationError,
    RateLimitExceeded
)

# Import routers
from app.api.endpoints import auth, users, projects, resources

settings = get_settings()

# Setup logging
setup_logging(
    log_level=settings.LOG_LEVEL,
    json_format=(settings.ENVIRONMENT == "production")
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting application in {settings.ENVIRONMENT} mode")

    # Initialize database tables (dev only - use Alembic in production)
    if settings.ENVIRONMENT == "development":
        logger.warning("Initializing database tables (dev mode)")
        init_db()

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application")
    # Cleanup resources (close DB connections, Redis, etc.)
    engine.dispose()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Multi-Tenant SaaS Platform",
    description="Production-grade multi-tenant SaaS with tenant isolation, RBAC, and rate limiting",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


# ============================================================================
# MIDDLEWARE CONFIGURATION
# ============================================================================

# CORS Middleware
# SECURITY: In production, restrict allowed_origins to specific domains
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
]

if settings.ENVIRONMENT == "development":
    allowed_origins.append("*")  # Allow all in dev (NOT for production!)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if settings.ENVIRONMENT != "development" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted Host Middleware (security)
# FIXME: Configure with actual allowed hosts in production
# if settings.ENVIRONMENT == "production":
#     app.add_middleware(
#         TrustedHostMiddleware,
#         allowed_hosts=["*.yourdomain.com", "yourdomain.com"]
#     )

# Request timing middleware (for monitoring)
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add X-Process-Time header to track request duration."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# CRITICAL: Tenant middleware must be added early
# It injects tenant context that other middleware/routes depend on
app.add_middleware(TenantMiddleware)

# Rate limiting middleware (after tenant middleware)
app.add_middleware(RateLimitMiddleware)


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(TenantIsolationError)
async def tenant_isolation_error_handler(request: Request, exc: TenantIsolationError):
    """
    Handle tenant isolation violations.

    CRITICAL: These should be logged and alerted on immediately.
    Tenant isolation violations are serious security issues.
    """
    logger.error(
        f"TENANT ISOLATION VIOLATION: {exc.detail}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "tenant_id": getattr(request.state, "tenant_id", None)
        }
    )

    # In production, trigger alert/notification here
    # send_security_alert("tenant_isolation_violation", {...})

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "type": "tenant_isolation_error"}
    )


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "type": "authentication_error"},
        headers=exc.headers or {}
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_error_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit errors."""
    logger.warning(
        f"Rate limit exceeded: {request.url.path}",
        extra={"tenant_id": getattr(request.state, "tenant_id", None)}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "type": "rate_limit_exceeded"},
        headers=exc.headers or {}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler.

    SECURITY: Don't expose internal errors in production.
    Log full details but return generic error to client.
    """
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method,
            "tenant_id": getattr(request.state, "tenant_id", None)
        }
    )

    if settings.DEBUG:
        # In debug mode, return full error details
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "traceback": "See logs for traceback"
            }
        )
    else:
        # In production, return generic error
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": "internal_error"
            }
        )


# ============================================================================
# ROUTES
# ============================================================================

# Health check endpoint (no auth required)
@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint for load balancers.

    TODO: Add more comprehensive checks:
    - Database connectivity
    - Redis connectivity
    - Disk space
    - Memory usage
    """
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Multi-Tenant SaaS Platform API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# Register API routers
# All routes will be under /api prefix for versioning
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(resources.router, prefix="/api/v1")


# ============================================================================
# STARTUP MESSAGE
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 80)
    logger.info("Multi-Tenant SaaS Platform")
    logger.info("=" * 80)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug: {settings.DEBUG}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
    logger.info("=" * 80)

    # Run with uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
