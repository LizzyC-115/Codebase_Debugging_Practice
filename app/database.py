"""
Database Configuration and Session Management

This module handles SQLAlchemy setup with connection pooling.
Connection pooling is critical for multi-tenant apps to avoid
creating too many database connections.

NOTE: We use a custom session factory that will be wrapped by
tenant-aware middleware to ensure proper isolation.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()

# SQLAlchemy engine with connection pooling
# Using QueuePool (default) with custom pool size for better concurrency
# TRADEOFF: Larger pool = more connections = more memory but better performance
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before using (handles stale connections)
    echo=settings.DEBUG,  # Log SQL in debug mode
)

# Session factory
# expire_on_commit=False is intentional here - we want to access object attributes
# after commit without hitting the database again. This is a performance optimization
# but can lead to stale data if not careful.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Performance optimization - be careful with stale data!
)

# Base class for all models
Base = declarative_base()


# Event listener for connection setup
# This ensures timezone is set consistently for all connections
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set connection-level configuration on new connections."""
    cursor = dbapi_connection.cursor()
    # Set timezone to UTC for consistency across all tenants (PostgreSQL only)
    # SQLite doesn't support SET TIME ZONE, so we skip it
    if settings.DATABASE_URL.startswith("postgresql"):
        cursor.execute("SET TIME ZONE 'UTC'")
    cursor.close()
    logger.debug("New database connection established")


def get_db() -> Session:
    """
    Dependency function that provides a database session.

    This is used with FastAPI's dependency injection system.
    The session is automatically closed after the request completes.

    NOTE: Tenant isolation is enforced at the middleware level,
    not here. This function just provides a raw session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.

    In production, you'd use Alembic migrations instead.
    This is here for dev/testing convenience but commented out
    to remind people to use proper migrations.
    """
    # DONT use this in production - use alembic migrations!
    # Base.metadata.create_all(bind=engine)
    logger.warning("init_db() called - use Alembic migrations in production!")
    Base.metadata.create_all(bind=engine)
