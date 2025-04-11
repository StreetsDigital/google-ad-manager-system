"""Tests for the retry mechanism implementation."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from src.campaigns.line_items.retry import (
    RetryConfig,
    RetryState,
    retryable,
    RetryableError,
    NetworkError,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError
)
from src.campaigns.line_items.processor import LineItemProcessor
from src.campaigns.line_items.connection_pool import ConnectionPool

@pytest.fixture
def retry_config():
    """Create a retry configuration for testing."""
    return RetryConfig(
        max_attempts=3,
        base_delay=0.1,  # Small delay for faster tests
        max_delay=1.0,
        exponential_base=2.0,
        jitter=False  # Disable jitter for predictable tests
    )

@pytest.fixture
def retry_state(retry_config):
    """Create a retry state for testing."""
    return RetryState(retry_config)

@pytest.fixture
def mock_connection_pool():
    pool = Mock(spec=ConnectionPool)
    pool.get_connection = AsyncMock()
    return pool

@pytest.fixture
def processor(mock_connection_pool):
    return LineItemProcessor(mock_connection_pool)

def test_retry_config_delay_calculation():
    """Test retry delay calculation."""
    config = RetryConfig(
        base_delay=1.0,
        max_delay=8.0,
        exponential_base=2.0,
        jitter=False
    )
    
    # Check exponential backoff
    assert config.calculate_delay(1) == 1.0  # 1 * (2^0)
    assert config.calculate_delay(2) == 2.0  # 1 * (2^1)
    assert config.calculate_delay(3) == 4.0  # 1 * (2^2)
    assert config.calculate_delay(4) == 8.0  # 1 * (2^3), capped at max_delay
    assert config.calculate_delay(5) == 8.0  # Still capped at max_delay

def test_retry_config_with_jitter():
    """Test that jitter adds randomness to delays."""
    config = RetryConfig(
        base_delay=1.0,
        jitter=True
    )
    
    # Get multiple delays and verify they're different
    delays = [config.calculate_delay(1) for _ in range(5)]
    assert len(set(delays)) > 1  # Should get different values due to jitter

def test_retry_state_tracking():
    """Test retry state tracking."""
    config = RetryConfig(max_attempts=3)
    state = RetryState(config)
    
    # Record some attempts
    error = NetworkError("Test error")
    state.record_attempt()  # Success
    state.record_attempt(error)  # Failure
    
    # Check state
    assert state.attempts == 2
    assert state.last_error == error
    assert len(state.errors) == 1
    assert isinstance(state.errors[0][0], datetime)
    assert state.errors[0][1] == error

def test_retry_state_should_retry():
    """Test retry decision logic."""
    config = RetryConfig(max_attempts=2)
    state = RetryState(config)
    
    # Should retry on first retryable error
    state.record_attempt()
    assert state.should_retry(RetryableError())
    
    # Should not retry after max attempts
    state.record_attempt()
    assert not state.should_retry(RetryableError())
    
    # Should not retry non-retryable errors
    state = RetryState(config)
    assert not state.should_retry(ValueError())

@pytest.mark.asyncio
async def test_retryable_decorator_success():
    """Test successful execution with retry decorator."""
    mock_func = Mock()
    mock_func.return_value = "success"
    
    @retryable()
    async def test_func():
        return mock_func()
    
    result = await test_func()
    assert result == "success"
    assert mock_func.call_count == 1

@pytest.mark.asyncio
async def test_retryable_decorator_retry_success():
    """Test successful retry after failures."""
    mock_func = Mock()
    mock_func.side_effect = [
        NetworkError("First failure"),
        NetworkError("Second failure"),
        "success"
    ]
    
    @retryable(RetryConfig(base_delay=0.1))
    async def test_func():
        return mock_func()
    
    result = await test_func()
    assert result == "success"
    assert mock_func.call_count == 3

@pytest.mark.asyncio
async def test_retryable_decorator_max_retries():
    """Test that max retries is respected."""
    mock_func = Mock(side_effect=NetworkError("Always fails"))
    
    @retryable(RetryConfig(max_attempts=3, base_delay=0.1))
    async def test_func():
        return mock_func()
    
    with pytest.raises(NetworkError):
        await test_func()
    assert mock_func.call_count == 3

@pytest.mark.asyncio
async def test_retryable_decorator_non_retryable():
    """Test that non-retryable errors are not retried."""
    mock_func = Mock(side_effect=ValueError("Non-retryable"))
    
    @retryable()
    async def test_func():
        return mock_func()
    
    with pytest.raises(ValueError):
        await test_func()
    assert mock_func.call_count == 1

@pytest.mark.asyncio
async def test_retryable_decorator_custom_errors():
    """Test retry with custom retryable errors."""
    mock_func = Mock(side_effect=[ValueError("Retry me"), "success"])
    
    @retryable(retryable_errors=(ValueError,))
    async def test_func():
        return mock_func()
    
    result = await test_func()
    assert result == "success"
    assert mock_func.call_count == 2

@pytest.mark.asyncio
async def test_retryable_decorator_exponential_backoff():
    """Test that exponential backoff delays are used."""
    mock_func = Mock(side_effect=[NetworkError("Retry")] * 3 + ["success"])
    start_time = datetime.now()
    
    @retryable(RetryConfig(
        max_attempts=4,
        base_delay=0.1,
        exponential_base=2.0,
        jitter=False
    ))
    async def test_func():
        return mock_func()
    
    result = await test_func()
    duration = (datetime.now() - start_time).total_seconds()
    
    assert result == "success"
    assert mock_func.call_count == 4
    # Expected delays: 0.1, 0.2, 0.4 = 0.7 total
    assert duration >= 0.7

@pytest.mark.asyncio
async def test_common_error_types():
    """Test all common retryable error types."""
    errors = [
        NetworkError("Network error"),
        RateLimitError("Rate limited"),
        ServiceUnavailableError("Service down"),
        TimeoutError("Timed out")
    ]
    
    for error in errors:
        mock_func = Mock(side_effect=[error, "success"])
        
        @retryable(RetryConfig(base_delay=0.1))
        async def test_func():
            return mock_func()
        
        result = await test_func()
        assert result == "success"
        assert mock_func.call_count == 2

@pytest.mark.asyncio
async def test_fetch_order_success(processor, mock_connection_pool):
    """Test successful order fetch without retries."""
    mock_conn = AsyncMock()
    mock_conn.get_order.return_value = {"id": "123", "status": "approved"}
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    result = await processor._fetch_order("123")
    
    assert result["id"] == "123"
    assert result["status"] == "approved"
    assert mock_conn.get_order.call_count == 1

@pytest.mark.asyncio
async def test_fetch_order_with_retries(processor, mock_connection_pool):
    """Test order fetch with retries on network error."""
    mock_conn = AsyncMock()
    mock_conn.get_order.side_effect = [
        NetworkError("Connection failed"),
        NetworkError("Connection failed"),
        {"id": "123", "status": "approved"}
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    result = await processor._fetch_order("123")
    
    assert result["id"] == "123"
    assert mock_conn.get_order.call_count == 3

@pytest.mark.asyncio
async def test_fetch_order_max_retries_exceeded(processor, mock_connection_pool):
    """Test order fetch fails after max retries."""
    mock_conn = AsyncMock()
    mock_conn.get_order.side_effect = NetworkError("Connection failed")
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    with pytest.raises(NetworkError):
        await processor._fetch_order("123")
    
    assert mock_conn.get_order.call_count == 3

@pytest.mark.asyncio
async def test_fetch_creatives_success(processor, mock_connection_pool):
    """Test successful creatives fetch."""
    mock_conn = AsyncMock()
    mock_conn.get_creatives.return_value = [
        {"id": "1", "active": True, "size": "300x250"},
        {"id": "2", "active": True, "size": "728x90"}
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    result = await processor._fetch_creatives(["1", "2"])
    
    assert len(result) == 2
    assert result[0]["id"] == "1"
    assert result[1]["id"] == "2"
    assert mock_conn.get_creatives.call_count == 1

@pytest.mark.asyncio
async def test_fetch_targeting_with_rate_limit(processor, mock_connection_pool):
    """Test targeting fetch with rate limit retries."""
    mock_conn = AsyncMock()
    mock_conn.get_targeting.side_effect = [
        RateLimitError("Rate limit exceeded"),
        {"rules": [{"id": "1", "criteria": {"key": "value"}}]}
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    result = await processor._fetch_targeting("123")
    
    assert "rules" in result
    assert len(result["rules"]) == 1
    assert mock_conn.get_targeting.call_count == 2

@pytest.mark.asyncio
async def test_create_line_item_with_timeout(processor, mock_connection_pool):
    """Test line item creation with timeout retries."""
    mock_conn = AsyncMock()
    mock_conn.create_line_item.side_effect = [
        TimeoutError("Request timed out"),
        {"id": "123", "status": "active"}
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    result = await processor._create_line_item({
        "orderId": "456",
        "name": "Test Line Item",
        "startDate": "2024-01-01",
        "endDate": "2024-12-31"
    })
    
    assert result["id"] == "123"
    assert result["status"] == "active"
    assert mock_conn.create_line_item.call_count == 2

@pytest.mark.asyncio
async def test_validate_order_constraints_with_service_unavailable(processor, mock_connection_pool):
    """Test order validation with service unavailable retries."""
    mock_conn = AsyncMock()
    mock_conn.get_order.side_effect = [
        ServiceUnavailableError("Service is down"),
        {"id": "123", "status": "approved", "startDate": "2024-01-01", "endDate": "2024-12-31"}
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    line_item = {
        "orderId": "123",
        "startDate": "2024-02-01",
        "endDate": "2024-11-30"
    }
    
    errors, order = await processor._validate_order_constraints(line_item)
    
    assert not errors
    assert order["id"] == "123"
    assert mock_conn.get_order.call_count == 2

@pytest.mark.asyncio
async def test_validate_creatives_with_mixed_errors(processor, mock_connection_pool):
    """Test creative validation with mixed error types."""
    mock_conn = AsyncMock()
    mock_conn.get_creatives.side_effect = [
        NetworkError("Connection failed"),
        RateLimitError("Rate limit exceeded"),
        [
            {"id": "1", "active": True, "size": "300x250"},
            {"id": "2", "active": False, "size": "300x250"}
        ]
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    line_item = {
        "creativeIds": ["1", "2"],
        "size": "300x250"
    }
    
    errors = await processor._validate_creatives(line_item)
    
    assert len(errors) == 1
    assert "Creative 2 is not active" in errors[0]
    assert mock_conn.get_creatives.call_count == 3

@pytest.mark.asyncio
async def test_exponential_backoff_timing(processor, mock_connection_pool):
    """Test exponential backoff timing between retries."""
    mock_conn = AsyncMock()
    mock_conn.get_order.side_effect = [
        NetworkError("Connection failed"),
        NetworkError("Connection failed"),
        {"id": "123", "status": "approved"}
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    start_time = datetime.now()
    result = await processor._fetch_order("123")
    end_time = datetime.now()
    
    # With base_delay=0.1 and exponential_base=2.0:
    # First retry after 0.1s
    # Second retry after 0.2s
    # Total expected delay ~= 0.3s
    expected_min_delay = timedelta(seconds=0.3)
    actual_delay = end_time - start_time
    
    assert actual_delay >= expected_min_delay
    assert result["id"] == "123"

@pytest.mark.asyncio
async def test_concurrent_retries(processor, mock_connection_pool):
    """Test multiple concurrent operations with retries."""
    mock_conn = AsyncMock()
    mock_conn.get_order.side_effect = [
        NetworkError("Connection failed"),
        {"id": "123", "status": "approved"}
    ]
    mock_conn.get_creatives.side_effect = [
        RateLimitError("Rate limit exceeded"),
        [{"id": "1", "active": True, "size": "300x250"}]
    ]
    mock_connection_pool.get_connection.return_value.__aenter__.return_value = mock_conn
    
    order_task = asyncio.create_task(processor._fetch_order("123"))
    creatives_task = asyncio.create_task(processor._fetch_creatives(["1"]))
    
    order_result, creatives_result = await asyncio.gather(order_task, creatives_task)
    
    assert order_result["id"] == "123"
    assert creatives_result[0]["id"] == "1"
    assert mock_conn.get_order.call_count == 2
    assert mock_conn.get_creatives.call_count == 2 