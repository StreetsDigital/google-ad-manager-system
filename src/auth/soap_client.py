"""
SOAP Client implementation for Google Ad Manager API.

This module provides a base SOAP client setup with error handling and configuration
management for interacting with the Google Ad Manager API.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import zeep
from zeep.transports import Transport
from requests import Session
from requests.adapters import HTTPAdapter, Retry
import logging
from datetime import datetime, timedelta
import os
from dataclasses import dataclass
from .errors import (
    AuthError, ConfigError, NetworkError, APIError,
    RetryStrategy, ErrorCategory, ErrorSeverity
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SoapClientConfig:
    """Configuration for SOAP client."""
    client_id: str
    client_secret: str
    refresh_token: Optional[str] = None
    network_code: Optional[str] = None
    application_name: str = "MCP_Test"
    wsdl_url: str = "https://ads.google.com/apis/ads/publisher/v202308/NetworkService?wsdl"
    timeout: int = 30
    max_retries: int = 3
    backoff_factor: float = 0.3
    retry_on_status: List[int] = None
    pool_connections: int = 10
    pool_maxsize: int = 10
    pool_block: bool = True

    def __post_init__(self):
        """Set default retry status codes if none provided."""
        if self.retry_on_status is None:
            self.retry_on_status = [500, 502, 503, 504]

class GoogleAdManagerClient:
    """
    SOAP client for Google Ad Manager API interactions.
    
    This class provides the base client setup with proper configuration,
    connection pooling, and error handling.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the client with configuration.
        
        Args:
            config: Configuration dictionary with required fields
        
        Raises:
            ConfigError: If configuration is invalid
        """
        try:
            # If config is already a SoapClientConfig instance, use it directly
            if isinstance(config, SoapClientConfig):
                self.config = config
            else:
                # Otherwise, create a new instance from the dictionary
                self.config = SoapClientConfig(**config)
            
            self._client = None
            self._session = None
            self._retry_strategy = RetryStrategy(
                max_retries=self.config.max_retries,
                base_delay=self.config.backoff_factor
            )
            self._setup_client()
            
        except Exception as e:
            raise ConfigError(
                message=f"Invalid client configuration: {str(e)}",
                operation="client_initialization",
                details={"config": config}
            )
    
    def _setup_client(self) -> None:
        """
        Set up the SOAP client with proper configuration and error handling.
        
        Raises:
            NetworkError: If client setup fails
            ConfigError: If configuration is invalid
        """
        try:
            # Create session with retry logic
            self._session = Session()
            retry_strategy = Retry(
                total=self.config.max_retries,
                backoff_factor=self.config.backoff_factor,
                status_forcelist=self.config.retry_on_status
            )
            
            # Configure connection pooling
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=self.config.pool_connections,
                pool_maxsize=self.config.pool_maxsize
            )
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
            
            # Create transport with timeout
            transport = Transport(
                session=self._session,
                timeout=self.config.timeout
            )
            
            # Initialize SOAP client
            self._client = zeep.Client(
                wsdl=self.config.wsdl_url,
                transport=transport
            )
            
            logger.info("SOAP client successfully initialized")
            
        except zeep.exceptions.Error as e:
            raise NetworkError(
                message=f"Failed to initialize SOAP client: {str(e)}",
                operation="client_setup",
                details={"wsdl_url": self.config.wsdl_url}
            )
        except Exception as e:
            raise ConfigError(
                message=f"Invalid client configuration: {str(e)}",
                operation="client_setup",
                details={"config": self.config.__dict__}
            )
    
    def execute_with_retry(self, operation: str, func: callable, *args, **kwargs) -> Any:
        """
        Execute a function with retry logic.
        
        Args:
            operation: Name of the operation being performed
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Any: Result of the function call
            
        Raises:
            AuthError: If the operation fails after all retries
        """
        self._retry_strategy.reset()
        last_error = None
        
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                
                if not self._retry_strategy.should_retry(e):
                    break
                    
                delay = self._retry_strategy.get_delay()
                logger.warning(
                    f"Operation {operation} failed, retrying in {delay:.2f}s: {str(e)}"
                )
                time.sleep(delay)
        
        # If we get here, we've exhausted retries or encountered a non-retryable error
        if isinstance(last_error, AuthError):
            raise last_error
            
        raise APIError(
            message=f"Operation {operation} failed: {str(last_error)}",
            operation=operation,
            details={
                "retry_count": self._retry_strategy.retry_count,
                "original_error": str(last_error)
            }
        )
    
    def get_client(self) -> zeep.Client:
        """
        Get the underlying SOAP client.
        
        Returns:
            zeep.Client: The SOAP client instance
            
        Raises:
            RuntimeError: If client is not initialized
        """
        if not self._client:
            raise RuntimeError("SOAP client not initialized")
        return self._client
    
    def get_last_error(self) -> Optional[Exception]:
        """
        Get the last error that occurred.
        
        Returns:
            Optional[Exception]: The last error or None if no error occurred
        """
        return self._retry_strategy.get_last_error()
    
    def close(self) -> None:
        """Close the client and clean up resources."""
        if self._session:
            self._session.close()
        self._client = None
        self._session = None
        logger.info("SOAP client closed and resources cleaned up") 