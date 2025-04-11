"""
Network monitoring module for tracking network health and metrics.

This module provides network monitoring capabilities including latency tracking,
DNS resolution times, connection states, and circuit breaker functionality.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import socket
import dns.resolver
from functools import wraps
from statistics import mean, stdev

logger = logging.getLogger(__name__)

@dataclass
class NetworkMetrics:
    """Network performance metrics."""
    latencies: List[float] = field(default_factory=list)
    dns_times: List[float] = field(default_factory=list)
    connection_errors: int = 0
    dns_errors: int = 0
    last_check: Optional[datetime] = None
    window_size: int = 100  # Keep last 100 measurements
    
    def add_latency(self, latency: float) -> None:
        """Add a latency measurement."""
        self.latencies.append(latency)
        if len(self.latencies) > self.window_size:
            self.latencies.pop(0)
    
    def add_dns_time(self, dns_time: float) -> None:
        """Add a DNS resolution time measurement."""
        self.dns_times.append(dns_time)
        if len(self.dns_times) > self.window_size:
            self.dns_times.pop(0)
    
    def get_average_latency(self) -> Optional[float]:
        """Get average latency over the window."""
        return mean(self.latencies) if self.latencies else None
    
    def get_latency_stdev(self) -> Optional[float]:
        """Get latency standard deviation over the window."""
        return stdev(self.latencies) if len(self.latencies) > 1 else None
    
    def get_average_dns_time(self) -> Optional[float]:
        """Get average DNS resolution time over the window."""
        return mean(self.dns_times) if self.dns_times else None

class CircuitBreaker:
    """Circuit breaker for network operations."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        half_open_timeout: int = 30
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            reset_timeout: Seconds before attempting to close circuit
            half_open_timeout: Seconds to wait in half-open state
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_timeout = half_open_timeout
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, or half-open
        self.lock = asyncio.Lock()
    
    async def record_failure(self) -> None:
        """Record a failure and potentially open the circuit."""
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.state == "closed" and self.failure_count >= self.failure_threshold:
                logger.warning("Circuit breaker opened due to too many failures")
                self.state = "open"
    
    async def record_success(self) -> None:
        """Record a success and potentially close the circuit."""
        async with self.lock:
            if self.state == "half-open":
                logger.info("Circuit breaker closed after successful test")
                self.state = "closed"
                self.failure_count = 0
    
    async def can_execute(self) -> bool:
        """Check if operation can be executed based on circuit state."""
        async with self.lock:
            if self.state == "closed":
                return True
                
            if self.state == "open":
                # Check if enough time has passed to try half-open
                if self.last_failure_time and \
                   (datetime.now() - self.last_failure_time).total_seconds() >= self.reset_timeout:
                    logger.info("Circuit breaker entering half-open state")
                    self.state = "half-open"
                    return True
                return False
                
            # Half-open state
            if (datetime.now() - self.last_failure_time).total_seconds() >= self.half_open_timeout:
                return True
            return False

class NetworkMonitor:
    """Network health and performance monitor."""
    
    def __init__(
        self,
        check_interval: int = 60,
        dns_timeout: float = 1.0,
        connection_timeout: float = 5.0
    ):
        """
        Initialize network monitor.
        
        Args:
            check_interval: Seconds between health checks
            dns_timeout: Timeout for DNS queries in seconds
            connection_timeout: Timeout for connection tests in seconds
        """
        self.check_interval = check_interval
        self.dns_timeout = dns_timeout
        self.connection_timeout = connection_timeout
        
        self.metrics = NetworkMetrics()
        self.circuit_breaker = CircuitBreaker()
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start network monitoring."""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Network monitoring started")
    
    async def stop(self) -> None:
        """Stop network monitoring."""
        if not self._running:
            return
            
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Network monitoring stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_network_health()
                self.metrics.last_check = datetime.now()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in network monitoring: {e}", exc_info=True)
                await asyncio.sleep(1)  # Brief pause before retrying
    
    async def _check_network_health(self) -> None:
        """Perform network health checks."""
        # Check DNS resolution
        start_time = datetime.now()
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.dns_timeout
            resolver.lifetime = self.dns_timeout
            await asyncio.get_event_loop().run_in_executor(
                None,
                resolver.resolve,
                "ads.google.com",
                "A"
            )
            dns_time = (datetime.now() - start_time).total_seconds()
            self.metrics.add_dns_time(dns_time)
        except Exception as e:
            logger.warning(f"DNS resolution failed: {e}")
            self.metrics.dns_errors += 1
        
        # Check connection
        start_time = datetime.now()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("ads.google.com", 443),
                timeout=self.connection_timeout
            )
            writer.close()
            await writer.wait_closed()
            
            latency = (datetime.now() - start_time).total_seconds()
            self.metrics.add_latency(latency)
            await self.circuit_breaker.record_success()
        except Exception as e:
            logger.warning(f"Connection test failed: {e}")
            self.metrics.connection_errors += 1
            await self.circuit_breaker.record_failure()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current network health status."""
        return {
            "average_latency": self.metrics.get_average_latency(),
            "latency_stdev": self.metrics.get_latency_stdev(),
            "average_dns_time": self.metrics.get_average_dns_time(),
            "connection_errors": self.metrics.connection_errors,
            "dns_errors": self.metrics.dns_errors,
            "circuit_breaker_state": self.circuit_breaker.state,
            "last_check": self.metrics.last_check.isoformat() if self.metrics.last_check else None
        }

def with_circuit_breaker(func):
    """Decorator to add circuit breaker functionality to a function."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if not await self.circuit_breaker.can_execute():
            raise Exception("Circuit breaker is open")
        try:
            result = await func(self, *args, **kwargs)
            await self.circuit_breaker.record_success()
            return result
        except Exception as e:
            await self.circuit_breaker.record_failure()
            raise
    return wrapper 