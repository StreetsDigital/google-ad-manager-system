"""Tests for the connection pool implementation."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.campaigns.line_items.connection_pool import ConnectionPool, ConnectionStats
from src.tools.soap_tools import SoapToolAdapter

@pytest.fixture
def mock_soap_adapter():
    """Create a mock SOAP adapter."""
    adapter = Mock(spec=SoapToolAdapter)
    async def mock_call(*args, **kwargs):
        return {"status": "success", "data": {}}
    adapter.__call__ = mock_call
    return adapter

@pytest.fixture
def connection_pool():
    """Create a connection pool for testing."""
    return ConnectionPool(
        max_connections=3,
        max_requests_per_second=5,
        error_threshold=3,
        health_check_interval=1,
        retry_delay=1
    )

@pytest.mark.asyncio
async def test_connection_stats_tracking():
    """Test that connection statistics are properly tracked."""
    stats = ConnectionStats()
    
    # Test success recording
    stats.record_success(0.1)
    assert stats.requests_count == 1
    assert stats.errors_count == 0
    assert stats.average_response_time == 0.1
    assert stats.last_success_time is not None
    
    # Test error recording
    stats.record_error()
    assert stats.requests_count == 1
    assert stats.errors_count == 1
    assert stats.last_error_time is not None

@pytest.mark.asyncio
async def test_connection_health_check():
    """Test connection health checking logic."""
    stats = ConnectionStats()
    
    # Should be healthy initially
    assert stats.is_healthy(error_threshold=3)
    
    # Record some errors
    for _ in range(3):
        stats.record_error()
    
    # Should be unhealthy now
    assert not stats.is_healthy(error_threshold=3)
    
    # Wait for window to pass
    stats.last_error_time = datetime.now() - timedelta(minutes=6)
    assert stats.is_healthy(error_threshold=3, window_minutes=5)

@pytest.mark.asyncio
async def test_pool_connection_creation():
    """Test that the pool creates new connections when needed."""
    pool = ConnectionPool(max_connections=2)
    
    # Get first connection
    conn1 = await pool.get_connection()
    assert len(pool.connections) == 1
    assert conn1 in pool.connection_stats
    
    # Get second connection
    conn2 = await pool.get_connection()
    assert len(pool.connections) == 2
    assert conn2 in pool.connection_stats
    assert conn1 != conn2

@pytest.mark.asyncio
async def test_pool_connection_reuse():
    """Test that the pool reuses existing connections."""
    pool = ConnectionPool(max_connections=1)
    
    # Get connection twice
    conn1 = await pool.get_connection()
    conn2 = await pool.get_connection()
    
    # Should get same connection
    assert conn1 == conn2
    assert len(pool.connections) == 1

@pytest.mark.asyncio
async def test_execute_request_success(mock_soap_adapter):
    """Test successful request execution."""
    pool = ConnectionPool(max_connections=1)
    pool.connections.append(mock_soap_adapter)
    pool.connection_stats[mock_soap_adapter] = ConnectionStats()
    
    result = await pool.execute_request(method="test_method", param="value")
    
    assert result["status"] == "success"
    stats = pool.connection_stats[mock_soap_adapter]
    assert stats.requests_count == 1
    assert stats.errors_count == 0

@pytest.mark.asyncio
async def test_execute_request_error(mock_soap_adapter):
    """Test error handling in request execution."""
    pool = ConnectionPool(max_connections=1)
    pool.connections.append(mock_soap_adapter)
    pool.connection_stats[mock_soap_adapter] = ConnectionStats()
    
    # Make the adapter raise an exception
    async def mock_error(*args, **kwargs):
        raise Exception("Test error")
    mock_soap_adapter.__call__ = mock_error
    
    with pytest.raises(Exception):
        await pool.execute_request(method="test_method")
    
    stats = pool.connection_stats[mock_soap_adapter]
    assert stats.requests_count == 0
    assert stats.errors_count == 1

@pytest.mark.asyncio
async def test_health_check_removal():
    """Test that unhealthy connections are removed."""
    pool = ConnectionPool(
        max_connections=2,
        error_threshold=2,
        health_check_interval=1
    )
    
    # Add two connections
    conn1 = await pool.get_connection()
    conn2 = await pool.get_connection()
    
    # Make one unhealthy
    stats = pool.connection_stats[conn1]
    stats.record_error()
    stats.record_error()
    
    # Wait for health check
    await asyncio.sleep(2)
    
    # Should have removed unhealthy connection
    assert len(pool.connections) == 1
    assert conn2 in pool.connections
    assert conn1 not in pool.connections

@pytest.mark.asyncio
async def test_pool_stats():
    """Test pool statistics calculation."""
    pool = ConnectionPool(max_connections=2)
    
    # Add two connections with different stats
    conn1 = await pool.get_connection()
    conn2 = await pool.get_connection()
    
    stats1 = pool.connection_stats[conn1]
    stats2 = pool.connection_stats[conn2]
    
    # Record some activity
    stats1.record_success(0.1)
    stats1.record_success(0.2)
    stats2.record_success(0.1)
    stats2.record_error()
    
    # Check stats
    pool_stats = pool.get_pool_stats()
    assert pool_stats["total_connections"] == 2
    assert pool_stats["healthy_connections"] == 2
    assert pool_stats["total_requests"] == 3
    assert pool_stats["total_errors"] == 1
    assert pool_stats["error_rate"] == 1/3 