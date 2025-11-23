"""
Logging Configuration

Structured logging setup with JSON output for production.

PRODUCTION NOTE: In real production, you'd want:
- Log aggregation (ELK, Datadog, etc.)
- Separate log levels for different modules
- Request ID tracking across services
- PII filtering/masking
- Log rotation and retention policies
"""
import logging
import sys
from typing import Any, Dict
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Makes logs machine-readable for log aggregation systems.
    This is a simplified version - production systems use libraries
    like python-json-logger or structlog.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "tenant_id"):
            log_data["tenant_id"] = record.tenant_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """
    Configure application logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format for structured logging

    NOTE: Call this once at application startup.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler
    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        # Human-readable format for development
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

    root_logger.addHandler(handler)

    # Reduce noise from noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Use this instead of logging.getLogger() for consistency.
    """
    return logging.getLogger(name)


# Security event logging
# IMPORTANT: Security events should be logged separately and monitored
def log_security_event(event_type: str, details: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Log security-related events.

    These should be monitored/alerted on in production.

    Event types:
    - failed_login: Failed authentication attempt
    - tenant_isolation_violation: Attempted cross-tenant access
    - rate_limit_exceeded: Rate limit hit
    - privilege_escalation: Attempted unauthorized action
    """
    log_data = {
        "security_event": True,
        "event_type": event_type,
        **details
    }

    # In production, this might go to a separate security log or SIEM
    logger.warning(f"SECURITY EVENT: {event_type}", extra=log_data)
