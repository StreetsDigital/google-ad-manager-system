"""Tests for the error handling system."""
import pytest
from datetime import datetime
from src.auth.errors import (
    ErrorSeverity,
    ErrorCategory,
    ErrorContext,
    AuthError,
    TokenError,
    InvalidTokenError,
    TokenRefreshError,
    ConfigError,
    NetworkError,
    APIError,
    ValidationError,
    RetryStrategy
)

def test_error_context():
    """Test error context creation and validation."""
    context = ErrorContext(
        timestamp=datetime.utcnow(),
        operation="test_operation",
        severity=ErrorSeverity.ERROR,
        category=ErrorCategory.AUTHENTICATION,
        retry_count=1,
        max_retries=3,
        details={"test": "value"}
    )
    
    assert context.operation == "test_operation"
    assert context.severity == ErrorSeverity.ERROR
    assert context.category == ErrorCategory.AUTHENTICATION
    assert context.retry_count == 1
    assert context.max_retries == 3
    assert context.details == {"test": "value"}

def test_auth_error():
    """Test base authentication error."""
    error = AuthError(
        message="Test error",
        severity=ErrorSeverity.ERROR,
        category=ErrorCategory.AUTHENTICATION,
        operation="test_operation",
        details={"test": "value"}
    )
    
    assert str(error) == "Test error"
    assert error.context.severity == ErrorSeverity.ERROR
    assert error.context.category == ErrorCategory.AUTHENTICATION
    
    error_dict = error.to_dict()
    assert error_dict["error"] == "Test error"
    assert error_dict["type"] == "AuthError"
    assert error_dict["context"]["operation"] == "test_operation"

def test_token_error():
    """Test token-related errors."""
    error = TokenError(
        message="Invalid token",
        operation="token_validation",
        details={"token_type": "access"}
    )
    
    assert str(error) == "Invalid token"
    assert error.context.category == ErrorCategory.AUTHENTICATION
    assert error.context.operation == "token_validation"
    assert error.context.details == {"token_type": "access"}

def test_network_error_severity():
    """Test network error severity based on retry count."""
    # First attempt should be WARNING
    error = NetworkError(
        message="Connection failed",
        retry_count=0,
        max_retries=3
    )
    assert error.context.severity == ErrorSeverity.WARNING
    
    # Last attempt should be ERROR
    error = NetworkError(
        message="Connection failed",
        retry_count=3,
        max_retries=3
    )
    assert error.context.severity == ErrorSeverity.ERROR

class TestRetryStrategy:
    """Test cases for retry strategy."""
    
    def test_initialization(self):
        """Test retry strategy initialization."""
        strategy = RetryStrategy(max_retries=3, base_delay=1.0)
        assert strategy.max_retries == 3
        assert strategy.base_delay == 1.0
        assert strategy.retry_count == 0
        assert strategy.get_last_error() is None

    def test_should_retry(self):
        """Test retry decision logic."""
        strategy = RetryStrategy(max_retries=3)
        
        # Should retry network errors
        assert strategy.should_retry(NetworkError("test"))
        
        # Should retry token refresh errors
        assert strategy.should_retry(TokenRefreshError("test"))
        
        # Should not retry validation errors
        assert not strategy.should_retry(ValidationError("test"))
        
        # Should not retry config errors
        assert not strategy.should_retry(ConfigError("test"))
        
        # Should not retry after max attempts
        strategy.retry_count = 3
        assert not strategy.should_retry(NetworkError("test"))

    def test_get_delay(self):
        """Test exponential backoff delay calculation."""
        strategy = RetryStrategy(base_delay=1.0)
        
        # First retry: 1.0 * 2^0 = 1.0
        assert strategy.get_delay() == 1.0
        
        # Second retry: 1.0 * 2^1 = 2.0
        assert strategy.get_delay() == 2.0
        
        # Third retry: 1.0 * 2^2 = 4.0
        assert strategy.get_delay() == 4.0

    def test_reset(self):
        """Test retry strategy reset."""
        strategy = RetryStrategy()
        strategy.retry_count = 2
        strategy._last_error = Exception("test")
        
        strategy.reset()
        assert strategy.retry_count == 0
        assert strategy.get_last_error() is None

def test_error_inheritance():
    """Test error class inheritance relationships."""
    # TokenError inherits from AuthError
    assert issubclass(TokenError, AuthError)
    
    # InvalidTokenError inherits from TokenError
    assert issubclass(InvalidTokenError, TokenError)
    
    # TokenRefreshError inherits from TokenError
    assert issubclass(TokenRefreshError, TokenError)
    
    # NetworkError inherits from AuthError
    assert issubclass(NetworkError, AuthError)
    
    # ConfigError inherits from AuthError
    assert issubclass(ConfigError, AuthError)
    
    # APIError inherits from AuthError
    assert issubclass(APIError, AuthError)
    
    # ValidationError inherits from AuthError
    assert issubclass(ValidationError, AuthError)

def test_api_error_with_status_code():
    """Test API error with status code in details."""
    error = APIError(
        message="API request failed",
        operation="test_api_call",
        status_code=404
    )
    
    assert error.context.details["status_code"] == 404
    assert "status_code" in error.to_dict()["context"]["details"] 