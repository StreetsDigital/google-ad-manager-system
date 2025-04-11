"""
Error handling module for authentication and SOAP operations.

This module provides a comprehensive error handling system including:
- Custom exception hierarchy
- Error classification
- Retry strategies
- Error logging
"""
from typing import Optional, Dict, Any, List, Type, Union, Callable
from enum import Enum
import logging
from datetime import datetime, UTC
from pydantic import BaseModel
import asyncio
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ErrorSeverity(str, Enum):
    """Severity levels for errors."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class ErrorCategory(str, Enum):
    """Categories of errors that can occur."""
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    CONFIGURATION = "configuration"
    API = "api"
    VALIDATION = "validation"
    SYSTEM = "system"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    SERVICE = "service"

class ErrorContext(BaseModel):
    """Context information for errors."""
    timestamp: datetime
    operation: str
    severity: ErrorSeverity
    category: ErrorCategory
    retry_count: int = 0
    max_retries: int = 3
    details: Dict[str, Any] = {}

class BaseError(Exception):
    """Base error class with common attributes."""
    def __init__(
        self,
        message: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None,
        category: ErrorCategory = ErrorCategory.API,
        severity: ErrorSeverity = ErrorSeverity.ERROR
    ):
        super().__init__(message)
        self.message = message
        self.operation = operation
        self.details = details or {}
        self.category = category
        self.severity = severity
        self.timestamp = datetime.now(UTC)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format."""
        return {
            "status": "error",
            "message": self.message,
            "operation": self.operation,
            "details": self.details,
            "category": self.category,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat()
        }

class AuthError(BaseError):
    """Authentication-related errors."""
    def __init__(
        self,
        message: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            operation=operation,
            details=details,
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.ERROR
        )

class ConfigError(BaseError):
    """Configuration-related errors."""
    def __init__(
        self,
        message: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            operation=operation,
            details=details,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.ERROR
        )

class NetworkError(BaseError):
    """Network-related errors."""
    def __init__(
        self,
        message: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            operation=operation,
            details=details,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.ERROR
        )

class APIError(BaseError):
    """API-related errors."""
    def __init__(
        self,
        message: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            operation=operation,
            details=details,
            category=ErrorCategory.API,
            severity=ErrorSeverity.ERROR
        )

class TokenError(AuthError):
    """Token-related errors."""
    pass

class InvalidTokenError(TokenError):
    """Invalid token errors."""
    pass

class TokenRefreshError(TokenError):
    """Token refresh errors."""
    pass

class ValidationError(AuthError):
    """Raised for validation errors."""
    def __init__(
        self,
        message: str,
        operation: str = "validation",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message,
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.VALIDATION,
            operation=operation,
            details=details
        )

class RetryableError(BaseError):
    """Base class for errors that can be retried."""
    pass

class RateLimitError(RetryableError):
    """Rate limit exceeded errors."""
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None
    ):
        super().__init__(
            message=message,
            operation=operation,
            details={
                **(details or {}),
                "retry_after": retry_after
            },
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.WARNING
        )

class ServiceUnavailableError(RetryableError):
    """Service unavailable errors."""
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            operation=operation,
            details=details,
            category=ErrorCategory.SERVICE,
            severity=ErrorSeverity.WARNING
        )

class TimeoutError(RetryableError):
    """Timeout errors."""
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ):
        super().__init__(
            message=message,
            operation=operation,
            details={
                **(details or {}),
                "timeout": timeout
            },
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.WARNING
        )

class RetryStrategy:
    """Strategy for retrying failed operations."""
    def __init__(self, max_retries: int = 3, base_delay: float = 0.1):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.attempts = 0
        self.last_error: Optional[Exception] = None

    def should_retry(self, error: Exception) -> bool:
        """Determine if operation should be retried."""
        self.last_error = error
        self.attempts += 1
        return self.attempts < self.max_retries

    def get_delay(self) -> float:
        """Get delay before next retry."""
        return self.base_delay * (2 ** (self.attempts - 1))

    def reset(self) -> None:
        """Reset retry counter."""
        self.attempts = 0
        self.last_error = None

    def get_last_error(self) -> Optional[Exception]:
        """Get the last error that occurred."""
        return self.last_error

def retryable(
    retry_config: Optional[Dict[str, Any]] = None,
    retryable_errors: Optional[List[Type[Exception]]] = None
):
    """
    Decorator for retryable async functions.
    
    Args:
        retry_config: Optional retry configuration
        retryable_errors: Optional list of error types to retry
        
    Returns:
        Decorated function with retry capability
    """
    if retry_config is None:
        retry_config = {
            "max_retries": 3,
            "base_delay": 0.1,
            "max_delay": 1.0,
            "backoff_factor": 2.0
        }

    if retryable_errors is None:
        retryable_errors = (RetryableError,)

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempts = 0
            max_retries = retry_config.get("max_retries", 3)
            base_delay = retry_config.get("base_delay", 0.1)
            backoff_factor = retry_config.get("backoff_factor", 2.0)
            max_delay = retry_config.get("max_delay", 1.0)

            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if not isinstance(e, retryable_errors) or attempts >= max_retries:
                        raise

                    delay = min(base_delay * (backoff_factor ** (attempts - 1)), max_delay)
                    await asyncio.sleep(delay)

        return wrapper
    return decorator 