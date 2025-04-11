"""Tests for the network monitoring module."""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from src.campaigns.line_items.network_monitor import (
    NetworkMetrics, CircuitBreaker, NetworkMonitor, with_circuit_breaker
)

@pytest.fixture
def network_metrics():
    """Create NetworkMetrics instance for testing."""
    return NetworkMetrics()

@pytest.fixture
def circuit_breaker():
    """Create CircuitBreaker instance for testing."""
    return CircuitBreaker(
        failure_threshold=3,
        reset_timeout=5,
        half_open_timeout=2
    )

@pytest.fixture
def network_monitor():
    """Create NetworkMonitor instance for testing."""
    return NetworkMonitor(
        check_interval=1,
        dns_timeout=0.5,
        connection_timeout=1.0
    )

class TestNetworkMetrics:
    """Test cases for NetworkMetrics."""

    def test_add_latency(self, network_metrics):
        """Test adding latency measurements."""
        network_metrics.add_latency(0.1)
        network_metrics.add_latency(0.2)
        assert len(network_metrics.latencies) == 2
        assert network_metrics.get_average_latency() == 0.15
        assert network_metrics.get_latency_stdev() is not None

    def test_add_dns_time(self, network_metrics):
        """Test adding DNS resolution time measurements."""
        network_metrics.add_dns_time(0.05)
        network_metrics.add_dns_time(0.07)
        assert len(network_metrics.dns_times) == 2
        assert network_metrics.get_average_dns_time() == 0.06

    def test_window_size_limit(self, network_metrics):
        """Test that measurements are limited to window size."""
        for i in range(network_metrics.window_size + 10):
            network_metrics.add_latency(0.1)
        assert len(network_metrics.latencies) == network_metrics.window_size

class TestCircuitBreaker:
    """Test cases for CircuitBreaker."""

    @pytest.mark.asyncio
    async def test_initial_state(self, circuit_breaker):
        """Test initial circuit breaker state."""
        assert circuit_breaker.state == "closed"
        assert await circuit_breaker.can_execute()

    @pytest.mark.asyncio
    async def test_open_on_failures(self, circuit_breaker):
        """Test circuit opens after threshold failures."""
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure()
        assert circuit_breaker.state == "open"
        assert not await circuit_breaker.can_execute()

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, circuit_breaker):
        """Test circuit enters half-open state after timeout."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure()
        
        # Set last failure time to past reset timeout
        circuit_breaker.last_failure_time = datetime.now() - timedelta(seconds=circuit_breaker.reset_timeout + 1)
        
        assert await circuit_breaker.can_execute()
        assert circuit_breaker.state == "half-open"

    @pytest.mark.asyncio
    async def test_close_on_success(self, circuit_breaker):
        """Test circuit closes after success in half-open state."""
        # Put circuit in half-open state
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure()
        circuit_breaker.state = "half-open"
        
        await circuit_breaker.record_success()
        assert circuit_breaker.state == "closed"
        assert circuit_breaker.failure_count == 0

class TestNetworkMonitor:
    """Test cases for NetworkMonitor."""

    @pytest.mark.asyncio
    async def test_start_stop(self, network_monitor):
        """Test starting and stopping the monitor."""
        await network_monitor.start()
        assert network_monitor._running
        assert network_monitor._task is not None
        
        await network_monitor.stop()
        assert not network_monitor._running
        assert network_monitor._task is None

    @pytest.mark.asyncio
    async def test_health_check_success(self, network_monitor):
        """Test successful health check."""
        with patch("asyncio.open_connection") as mock_connect, \
             patch("dns.resolver.Resolver.resolve") as mock_resolve:
            
            # Mock successful connection
            mock_writer = AsyncMock()
            mock_connect.return_value = (None, mock_writer)
            
            # Mock successful DNS resolution
            mock_resolve.return_value = ["1.2.3.4"]
            
            await network_monitor._check_network_health()
            
            assert network_monitor.metrics.connection_errors == 0
            assert network_monitor.metrics.dns_errors == 0
            assert len(network_monitor.metrics.latencies) == 1
            assert len(network_monitor.metrics.dns_times) == 1

    @pytest.mark.asyncio
    async def test_health_check_failure(self, network_monitor):
        """Test health check with failures."""
        with patch("asyncio.open_connection") as mock_connect, \
             patch("dns.resolver.Resolver.resolve") as mock_resolve:
            
            # Mock connection failure
            mock_connect.side_effect = ConnectionError("Connection failed")
            
            # Mock DNS failure
            mock_resolve.side_effect = Exception("DNS resolution failed")
            
            await network_monitor._check_network_health()
            
            assert network_monitor.metrics.connection_errors == 1
            assert network_monitor.metrics.dns_errors == 1
            assert len(network_monitor.metrics.latencies) == 0
            assert len(network_monitor.metrics.dns_times) == 0

    def test_get_health_status(self, network_monitor):
        """Test getting health status."""
        # Add some test data
        network_monitor.metrics.add_latency(0.1)
        network_monitor.metrics.add_dns_time(0.05)
        network_monitor.metrics.connection_errors = 1
        network_monitor.metrics.dns_errors = 1
        network_monitor.metrics.last_check = datetime.now()
        
        status = network_monitor.get_health_status()
        
        assert "average_latency" in status
        assert "average_dns_time" in status
        assert "connection_errors" in status
        assert "dns_errors" in status
        assert "circuit_breaker_state" in status
        assert "last_check" in status

class TestCircuitBreakerDecorator:
    """Test cases for circuit breaker decorator."""

    class TestService:
        """Test service class."""
        def __init__(self):
            self.circuit_breaker = CircuitBreaker()

        @with_circuit_breaker
        async def test_method(self):
            """Test method with circuit breaker."""
            return "success"

    @pytest.mark.asyncio
    async def test_decorator_success(self):
        """Test successful execution with decorator."""
        service = self.TestService()
        result = await service.test_method()
        assert result == "success"
        assert service.circuit_breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_decorator_failure(self):
        """Test failure handling with decorator."""
        service = self.TestService()
        
        # Force circuit to open
        for _ in range(service.circuit_breaker.failure_threshold):
            await service.circuit_breaker.record_failure()
        
        with pytest.raises(Exception, match="Circuit breaker is open"):
            await service.test_method() 