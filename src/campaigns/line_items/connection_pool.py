"""
Connection pool implementation for SOAP client with rate limiting and health monitoring.

This module provides a connection pool for managing SOAP client connections,
including rate limiting, health checks, and automatic recovery.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from functools import wraps

from src.tools.soap_tools import SoapToolAdapter
from .network_monitor import NetworkMonitor, with_circuit_breaker

logger = logging.getLogger(__name__)

class ConnectionStats:
    """Tracks statistics for a connection."""
    
    def __init__(self):
        self.requests_count: int = 0
        self.errors_count: int = 0
        self.last_error_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        self.average_response_time: float = 0.0
        self.total_response_time: float = 0.0
        
    def record_success(self, response_time: float):
        """Record a successful request."""
        self.requests_count += 1
        self.last_success_time = datetime.now()
        self.total_response_time += response_time
        self.average_response_time = self.total_response_time / self.requests_count
        
    def record_error(self):
        """Record a failed request."""
        self.errors_count += 1
        self.last_error_time = datetime.now()
        
    def is_healthy(self, error_threshold: int = 5, window_minutes: int = 5) -> bool:
        """Check if the connection is healthy based on recent errors."""
        if self.errors_count == 0:
            return True
            
        if self.last_error_time is None:
            return True
            
        # Check if we're over the error threshold in the time window
        window_start = datetime.now() - timedelta(minutes=window_minutes)
        if self.last_error_time > window_start and self.errors_count >= error_threshold:
            return False
            
        return True

class ConnectionPool:
    """Manages a pool of SOAP client connections with rate limiting and health monitoring."""
    
    def __init__(
        self,
        max_connections: int = 5,
        max_requests_per_second: int = 3,
        error_threshold: int = 5,
        health_check_interval: int = 300,
        retry_delay: int = 5,
        dns_timeout: float = 1.0,
        connection_timeout: float = 5.0
    ):
        """
        Initialize the connection pool.
        
        Args:
            max_connections: Maximum number of connections in the pool
            max_requests_per_second: Maximum requests per second per connection
            error_threshold: Number of errors before marking connection unhealthy
            health_check_interval: Seconds between health checks
            retry_delay: Seconds to wait before retrying after error
            dns_timeout: Timeout for DNS queries in seconds
            connection_timeout: Timeout for connection tests in seconds
        """
        self.max_connections = max_connections
        self.max_requests_per_second = max_requests_per_second
        self.error_threshold = error_threshold
        self.health_check_interval = health_check_interval
        self.retry_delay = retry_delay
        
        self.connections: List[SoapToolAdapter] = []
        self.connection_stats: Dict[SoapToolAdapter, ConnectionStats] = {}
        self.current_connection_index = 0
        self.lock = asyncio.Lock()
        
        # Initialize network monitor
        self.network_monitor = NetworkMonitor(
            check_interval=health_check_interval,
            dns_timeout=dns_timeout,
            connection_timeout=connection_timeout
        )
        
        # Start health check loop and network monitoring
        asyncio.create_task(self._health_check_loop())
        asyncio.create_task(self.network_monitor.start())
        
    async def get_connection(self) -> SoapToolAdapter:
        """Get the next available healthy connection."""
        async with self.lock:
            # Check network health before creating/returning connection
            health_status = self.network_monitor.get_health_status()
            if health_status["circuit_breaker_state"] == "open":
                raise Exception("Network is currently unavailable")
            
            # Create new connection if needed and possible
            if len(self.connections) < self.max_connections:
                connection = SoapToolAdapter()
                self.connections.append(connection)
                self.connection_stats[connection] = ConnectionStats()
                return connection
            
            # Find next healthy connection
            start_index = self.current_connection_index
            while True:
                self.current_connection_index = (self.current_connection_index + 1) % len(self.connections)
                connection = self.connections[self.current_connection_index]
                
                if self.connection_stats[connection].is_healthy(self.error_threshold):
                    return connection
                    
                # If we've checked all connections, wait and retry
                if self.current_connection_index == start_index:
                    logger.warning("No healthy connections available, waiting to retry...")
                    await asyncio.sleep(self.retry_delay)
    
    @with_circuit_breaker
    async def execute_request(self, method: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a request using a connection from the pool.
        
        Args:
            method: The SOAP method to call
            **kwargs: Arguments for the method
            
        Returns:
            Response from the SOAP method
        """
        connection = await self.get_connection()
        stats = self.connection_stats[connection]
        
        start_time = datetime.now()
        try:
            result = await connection(method=method, **kwargs)
            
            # Record success statistics
            elapsed = (datetime.now() - start_time).total_seconds()
            stats.record_success(elapsed)
            self.network_monitor.metrics.add_latency(elapsed)
            
            return result
            
        except Exception as e:
            # Record error statistics
            stats.record_error()
            self.network_monitor.metrics.connection_errors += 1
            logger.error(f"Error executing request: {e}", exc_info=True)
            raise
    
    async def _health_check_loop(self):
        """Periodically check connection health and clean up if needed."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                async with self.lock:
                    # Get network health status
                    health_status = self.network_monitor.get_health_status()
                    logger.info(f"Network health status: {health_status}")
                    
                    for connection in list(self.connections):  # Create copy to allow modification
                        stats = self.connection_stats[connection]
                        
                        if not stats.is_healthy(self.error_threshold):
                            logger.warning(f"Removing unhealthy connection with {stats.errors_count} errors")
                            self.connections.remove(connection)
                            del self.connection_stats[connection]
                            
            except Exception as e:
                logger.error(f"Error in health check loop: {e}", exc_info=True)
                
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get statistics for all connections in the pool."""
        total_requests = 0
        total_errors = 0
        total_connections = len(self.connections)
        healthy_connections = 0
        
        for connection in self.connections:
            stats = self.connection_stats[connection]
            total_requests += stats.requests_count
            total_errors += stats.errors_count
            if stats.is_healthy(self.error_threshold):
                healthy_connections += 1
                
        # Include network health metrics
        network_status = self.network_monitor.get_health_status()
                
        return {
            "total_connections": total_connections,
            "healthy_connections": healthy_connections,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": (total_errors / total_requests) if total_requests > 0 else 0,
            "network_status": network_status
        }
    
    async def close(self):
        """Close the connection pool and stop monitoring."""
        await self.network_monitor.stop()
        for connection in self.connections:
            await connection.close() 