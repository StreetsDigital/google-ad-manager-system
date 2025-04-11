"""Tests for the connection pool implementation."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from src.campaigns.line_items.connection_pool import ConnectionPool, ConnectionStats
from src.tools.soap_tools import SoapToolAdapter
from src.campaigns.line_items.network_monitor import NetworkMonitor

@pytest.fixture
def mock_soap_adapter():
    """Create a mock SOAP adapter."""
    adapter = Mock(spec=SoapToolAdapter)
    async def mock_call(*args, **kwargs):
        return {"status": "success", "data": {}}
    adapter.__call__ = AsyncMock(side_effect=mock_call)
    adapter.close = AsyncMock()
    return adapter

@pytest.fixture
def mock_network_monitor():
    """Create a mock network monitor."""
    monitor = AsyncMock(spec=NetworkMonitor)
    monitor.get_health_status.return_value = {
        "average_latency": 0.1,
        "latency_stdev": 0.02,
        "average_dns_time": 0.05,
        "connection_errors": 0,
        "dns_errors": 0,
        "circuit_breaker_state": "closed",
        "last_check": datetime.now().isoformat()
    }
    return monitor

@pytest.fixture
def connection_pool(mock_network_monitor):
    """Create a connection pool for testing."""
    with patch("src.campaigns.line_items.connection_pool.NetworkMonitor", return_value=mock_network_monitor):
        pool = ConnectionPool(
            max_connections=3,
            max_requests_per_second=5,
            error_threshold=3,
            health_check_interval=1,
            retry_delay=1
        )
        return pool

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
async def test_pool_connection_creation(connection_pool, mock_soap_adapter):
    """Test that the pool creates new connections when needed."""
    with patch("src.campaigns.line_items.connection_pool.SoapToolAdapter", return_value=mock_soap_adapter):
        # Get first connection
        conn1 = await connection_pool.get_connection()
        assert len(connection_pool.connections) == 1
        assert conn1 in connection_pool.connection_stats
        
        # Get second connection
        conn2 = await connection_pool.get_connection()
        assert len(connection_pool.connections) == 2
        assert conn2 in connection_pool.connection_stats
        assert conn1 != conn2

@pytest.mark.asyncio
async def test_pool_connection_reuse(connection_pool, mock_soap_adapter):
    """Test that the pool reuses existing connections."""
    with patch("src.campaigns.line_items.connection_pool.SoapToolAdapter", return_value=mock_soap_adapter):
        # Get connection twice
        conn1 = await connection_pool.get_connection()
        conn2 = await connection_pool.get_connection()
        
        # Should get same connection
        assert conn1 == conn2
        assert len(connection_pool.connections) == 1

@pytest.mark.asyncio
async def test_execute_request_success(connection_pool, mock_soap_adapter):
    """Test successful request execution."""
    with patch("src.campaigns.line_items.connection_pool.SoapToolAdapter", return_value=mock_soap_adapter):
        connection_pool.connections.append(mock_soap_adapter)
        connection_pool.connection_stats[mock_soap_adapter] = ConnectionStats()
        
        result = await connection_pool.execute_request(method="test_method", param="value")
        
        assert result["status"] == "success"
        stats = connection_pool.connection_stats[mock_soap_adapter]
        assert stats.requests_count == 1
        assert stats.errors_count == 0

@pytest.mark.asyncio
async def test_execute_request_error(connection_pool, mock_soap_adapter):
    """Test error handling in request execution."""
    with patch("src.campaigns.line_items.connection_pool.SoapToolAdapter", return_value=mock_soap_adapter):
        connection_pool.connections.append(mock_soap_adapter)
        connection_pool.connection_stats[mock_soap_adapter] = ConnectionStats()
        
        # Make the adapter raise an exception
        mock_soap_adapter.__call__.side_effect = Exception("Test error")
        
        with pytest.raises(Exception):
            await connection_pool.execute_request(method="test_method")
        
        stats = connection_pool.connection_stats[mock_soap_adapter]
        assert stats.requests_count == 0
        assert stats.errors_count == 1

@pytest.mark.asyncio
async def test_health_check_removal(connection_pool, mock_soap_adapter):
    """Test that unhealthy connections are removed."""
    with patch("src.campaigns.line_items.connection_pool.SoapToolAdapter", return_value=mock_soap_adapter):
        # Add two connections
        conn1 = await connection_pool.get_connection()
        conn2 = await connection_pool.get_connection()
        
        # Make one unhealthy
        stats = connection_pool.connection_stats[conn1]
        stats.record_error()
        stats.record_error()
        stats.record_error()
        
        # Wait for health check
        await asyncio.sleep(2)
        
        # Should have removed unhealthy connection
        assert len(connection_pool.connections) == 1
        assert conn2 in connection_pool.connections
        assert conn1 not in connection_pool.connections

@pytest.mark.asyncio
async def test_network_monitoring_integration(connection_pool, mock_network_monitor):
    """Test integration with network monitoring."""
    # Test successful request with network monitoring
    result = await connection_pool.execute_request(method="test_method")
    assert result["status"] == "success"
    
    # Verify network monitor was called
    mock_network_monitor.get_health_status.assert_called()
    
    # Test with circuit breaker open
    mock_network_monitor.get_health_status.return_value["circuit_breaker_state"] = "open"
    with pytest.raises(Exception, match="Network is currently unavailable"):
        await connection_pool.get_connection()

@pytest.mark.asyncio
async def test_pool_stats_with_network_status(connection_pool, mock_network_monitor):
    """Test pool statistics including network status."""
    # Add some test data
    connection = await connection_pool.get_connection()
    stats = connection_pool.connection_stats[connection]
    stats.record_success(0.1)
    stats.record_error()
    
    pool_stats = connection_pool.get_pool_stats()
    
    assert pool_stats["total_connections"] == 1
    assert pool_stats["total_requests"] == 1
    assert pool_stats["total_errors"] == 1
    assert "network_status" in pool_stats
    assert pool_stats["network_status"]["circuit_breaker_state"] == "closed"

@pytest.mark.asyncio
async def test_pool_close(connection_pool, mock_network_monitor, mock_soap_adapter):
    """Test closing the connection pool."""
    with patch("src.campaigns.line_items.connection_pool.SoapToolAdapter", return_value=mock_soap_adapter):
        # Add a connection
        await connection_pool.get_connection()
        
        # Close the pool
        await connection_pool.close()
        
        # Verify network monitor was stopped
        mock_network_monitor.stop.assert_called_once()
        
        # Verify connections were closed
        mock_soap_adapter.close.assert_called_once() 