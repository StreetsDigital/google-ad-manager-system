"""
SOAP Tool Adapter for integrating Google Ad Manager SOAP client with MCP.

This module provides a tool adapter that wraps the GoogleAdManagerClient for use
with the MCP server, exposing SOAP operations as tools.
"""
import logging
import asyncio
from typing import Any, Dict, Optional, List, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime

from src.tools.tool_registry import ToolRegistry
from src.auth.soap_client import GoogleAdManagerClient, SoapClientConfig
from src.auth.errors import (
    AuthError, ConfigError, NetworkError, APIError,
    TokenError, InvalidTokenError, TokenRefreshError
)

# Configure logging
logger = logging.getLogger(__name__)

class BatchConfig(BaseModel):
    """Configuration for batch operations."""
    max_batch_size: int = Field(default=100, ge=1, le=500, description="Maximum operations per batch")
    concurrent_batches: int = Field(default=3, ge=1, le=10, description="Maximum concurrent batch executions")
    timeout_seconds: int = Field(default=300, description="Batch operation timeout in seconds")

class RetryConfig(BaseModel):
    """Configuration for retry behavior."""
    max_retries: int = Field(default=3, ge=0, description="Maximum number of retry attempts")
    backoff_factor: float = Field(default=0.3, ge=0, description="Backoff factor between retries")
    retry_on_status: List[int] = Field(
        default=[408, 429, 500, 502, 503, 504],
        description="HTTP status codes to retry on"
    )

class PoolConfig(BaseModel):
    """Configuration for connection pooling."""
    pool_connections: int = Field(default=10, ge=1, description="Number of connection pools")
    pool_maxsize: int = Field(default=10, ge=1, description="Maximum size of each pool")
    max_retries: int = Field(default=3, ge=0, description="Maximum retries per request")
    pool_block: bool = Field(default=False, description="Whether to block when pool is full")

class SoapToolConfig(BaseModel):
    """Complete configuration for SOAP tool adapter."""
    retry: RetryConfig = Field(default_factory=RetryConfig)
    pool: PoolConfig = Field(default_factory=PoolConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)
    client: Dict[str, Any] = Field(..., description="Google Ad Manager client configuration")

class BatchOperation(BaseModel):
    """Represents a single operation in a batch."""
    id: str
    method: str
    params: Dict[str, Any]
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

class BatchRequest(BaseModel):
    """Represents a batch of operations."""
    batch_id: str
    operations: List[BatchOperation]
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_operations: int = 0
    completed_operations: int = 0
    failed_operations: int = 0

    @validator("operations")
    def validate_operations(cls, v):
        """Validate operations list is not empty."""
        if not v:
            raise ValueError("Batch must contain at least one operation")
        return v

class SoapToolAdapter:
    """Adapter for integrating SOAP client with MCP tools."""

    def __init__(self, registry: ToolRegistry):
        """Initialize the adapter with a tool registry."""
        self.registry = registry
        self._client: Optional[GoogleAdManagerClient] = None
        self._config: Optional[SoapToolConfig] = None
        self._last_error: Optional[Exception] = None
        self._batch_requests: Dict[str, BatchRequest] = {}
        self._batch_semaphore: Optional[asyncio.Semaphore] = None

    @property
    def client(self) -> GoogleAdManagerClient:
        """Get the SOAP client instance, raising an error if not initialized."""
        if self._client is None:
            raise RuntimeError("SOAP client not initialized")
        return self._client

    @property
    def config(self) -> SoapToolConfig:
        """Get the current configuration, raising an error if not initialized."""
        if self._config is None:
            raise RuntimeError("SOAP tool not configured")
        return self._config

    async def initialize_client(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize the SOAP client with the provided configuration.
        
        Args:
            config: Dictionary containing client configuration
            
        Returns:
            Dict containing status and error message if applicable
        """
        try:
            # Parse and validate complete configuration
            tool_config = SoapToolConfig(
                client=config.get("client", {}),
                retry=RetryConfig(**(config.get("retry", {}))),
                pool=PoolConfig(**(config.get("pool", {})))
            )
            
            # Validate required fields
            required_fields = ['client_id', 'client_secret', 'refresh_token', 'network_code']
            missing_fields = [field for field in required_fields if field not in tool_config.client]
            
            if missing_fields:
                error = ConfigError(
                    message=f"Missing required configuration fields: {', '.join(missing_fields)}",
                    operation="client_initialization",
                    details={"missing_fields": missing_fields}
                )
                return {
                    "status": "error",
                    "message": error.message,
                    "details": error.details
                }

            # Create client configuration with retry and pool settings
            client_config = SoapClientConfig(
                **tool_config.client,
                max_retries=tool_config.retry.max_retries,
                backoff_factor=tool_config.retry.backoff_factor,
                retry_on_status=tool_config.retry.retry_on_status,
                pool_connections=tool_config.pool.pool_connections,
                pool_maxsize=tool_config.pool.pool_maxsize,
                pool_block=tool_config.pool.pool_block
            )
                
            self._client = GoogleAdManagerClient(client_config)
            self._config = tool_config
            self._last_error = None

            logger.info("SOAP client initialized successfully with retry and pool configuration")
            
            return {
                "status": "success",
                "message": "SOAP client initialized successfully",
                "config": {
                    "retry": tool_config.retry.model_dump(),
                    "pool": tool_config.pool.model_dump()
                }
            }
            
        except AuthError as e:
            self._last_error = e
            logger.error(f"Authentication error during client initialization: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "details": e.details
            }
        except Exception as e:
            self._last_error = e
            logger.error(f"Failed to initialize SOAP client: {str(e)}")
            error = APIError(
                message=f"Failed to initialize SOAP client: {str(e)}",
                operation="client_initialization",
                details={"config": {k: v for k, v in config.items() if k != "client_secret"}}
            )
            return {
                "status": "error",
                "message": error.message,
                "details": error.details
            }

    async def _execute_batch_operation(self, operation: BatchOperation) -> None:
        """Execute a single operation in a batch."""
        try:
            service = self.client.get_client().service
            method_func = getattr(service, operation.method, None)
            
            if method_func is None:
                raise APIError(
                    message=f"Invalid SOAP method: {operation.method}",
                    operation=f"soap.{operation.method}",
                    details={"available_methods": dir(service)}
                )
            
            logger.info(f"Executing batch operation {operation.id}: {operation.method}")
            
            result = await asyncio.wait_for(
                self.client.execute_with_retry(
                    operation=f"soap.{operation.method}",
                    func=method_func,
                    **operation.params
                ),
                timeout=self.config.batch.timeout_seconds
            )
            
            operation.status = "completed"
            operation.result = result
            
        except Exception as e:
            operation.status = "failed"
            operation.error = str(e)
            logger.error(f"Batch operation {operation.id} failed: {str(e)}")
        finally:
            operation.updated_at = datetime.utcnow()

    async def _execute_batch(self, batch: BatchRequest) -> None:
        """Execute a batch of operations with concurrency control."""
        if self._batch_semaphore is None:
            self._batch_semaphore = asyncio.Semaphore(self.config.batch.concurrent_batches)
        
        async with self._batch_semaphore:
            try:
                batch.status = "running"
                tasks = []
                
                for operation in batch.operations:
                    if len(tasks) >= self.config.batch.max_batch_size:
                        # Wait for current tasks to complete before adding more
                        await asyncio.gather(*tasks)
                        tasks = []
                    
                    task = asyncio.create_task(self._execute_batch_operation(operation))
                    tasks.append(task)
                
                # Wait for remaining tasks
                if tasks:
                    await asyncio.gather(*tasks)
                
                # Update batch statistics
                batch.completed_operations = sum(1 for op in batch.operations if op.status == "completed")
                batch.failed_operations = sum(1 for op in batch.operations if op.status == "failed")
                batch.status = "completed"
                
            except Exception as e:
                batch.status = "failed"
                logger.error(f"Batch {batch.batch_id} failed: {str(e)}")
            finally:
                batch.completed_at = datetime.utcnow()

    def register_tools(self) -> None:
        """Register SOAP-related tools with the registry."""
        
        @self.registry.register(
            name="soap.initialize",
            description="Initialize the SOAP client with configuration"
        )
        async def initialize_soap(config: Dict[str, Any]) -> Dict[str, Any]:
            """Initialize the SOAP client with the provided configuration."""
            return await self.initialize_client(config)

        @self.registry.register(
            name="soap.execute",
            description="Execute a SOAP method with parameters"
        )
        async def execute_soap_method(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
            """Execute a SOAP method with the provided parameters."""
            try:
                service = self.client.get_client().service
                method_func = getattr(service, method, None)
                
                if method_func is None:
                    raise APIError(
                        message=f"Invalid SOAP method: {method}",
                        operation=f"soap.{method}",
                        details={"available_methods": dir(service)}
                    )
                
                logger.info(f"Executing SOAP method {method} with params: {params}")
                
                result = await self.client.execute_with_retry(
                    operation=f"soap.{method}",
                    func=method_func,
                    **params
                )
                
                return {
                    "status": "success",
                    "data": result
                }
                
            except AuthError as e:
                self._last_error = e
                logger.error(f"Authentication error during method execution: {str(e)}")
                return e.to_dict()
            except Exception as e:
                self._last_error = e
                logger.error(f"Failed to execute SOAP method: {str(e)}")
                error = APIError(
                    message=f"Failed to execute SOAP method: {str(e)}",
                    operation=f"soap.{method}",
                    details={"method": method, "params": params}
                )
                return error.to_dict()

        @self.registry.register(
            name="soap.status",
            description="Get the current status of the SOAP client"
        )
        async def get_soap_status() -> Dict[str, Any]:
            """Get the current status of the SOAP client."""
            try:
                client = self.client
                config = self.config
                
                status_info = {
                    "status": "active",
                    "message": "SOAP client is initialized and ready",
                    "config": {
                        "retry": config.retry.model_dump(),
                        "pool": config.pool.model_dump(),
                        "client": {
                            k: "***" if k in ["client_secret", "refresh_token"] 
                            else v for k, v in config.client.items()
                        }
                    },
                    "last_error": str(self._last_error) if self._last_error else None,
                    "metrics": {
                        "active_connections": client.get_active_connections(),
                        "request_count": client.get_request_count(),
                        "error_count": client.get_error_count()
                    }
                }
                
                return status_info
                
            except RuntimeError as e:
                logger.error(f"Error getting SOAP client status: {str(e)}")
                error = ConfigError(
                    message="SOAP client not initialized",
                    operation="get_status"
                )
                return error.to_dict()

        @self.registry.register(
            name="soap.batch",
            description="Execute multiple SOAP operations in a batch"
        )
        async def execute_batch(operations: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Execute multiple SOAP operations in a batch."""
            try:
                # Validate batch size
                if len(operations) > self.config.batch.max_batch_size:
                    raise ConfigError(
                        message=f"Batch size exceeds maximum of {self.config.batch.max_batch_size}",
                        operation="soap.batch",
                        details={"max_size": self.config.batch.max_batch_size, "received": len(operations)}
                    )
                
                # Create batch request
                batch_ops = [BatchOperation(**op) for op in operations]
                batch_id = f"batch_{len(self._batch_requests) + 1}"
                batch = BatchRequest(
                    batch_id=batch_id,
                    operations=batch_ops,
                    total_operations=len(operations)
                )
                
                # Store batch request
                self._batch_requests[batch_id] = batch
                
                # Execute batch asynchronously
                asyncio.create_task(self._execute_batch(batch))
                
                return {
                    "status": "accepted",
                    "message": "Batch execution started",
                    "batch_id": batch_id
                }
                
            except Exception as e:
                self._last_error = e
                logger.error(f"Failed to start batch execution: {str(e)}")
                error = APIError(
                    message=f"Failed to start batch execution: {str(e)}",
                    operation="soap.batch",
                    details={"operations_count": len(operations)}
                )
                return error.to_dict()

        @self.registry.register(
            name="soap.batch.status",
            description="Get the status of a batch operation"
        )
        async def get_batch_status(batch_id: str) -> Dict[str, Any]:
            """Get the status of a batch operation."""
            try:
                batch = self._batch_requests.get(batch_id)
                if not batch:
                    raise ConfigError(
                        message=f"Batch {batch_id} not found",
                        operation="soap.batch.status"
                    )
                
                return {
                    "status": batch.status,
                    "batch_id": batch.batch_id,
                    "created_at": batch.created_at.isoformat(),
                    "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
                    "total_operations": batch.total_operations,
                    "completed_operations": batch.completed_operations,
                    "failed_operations": batch.failed_operations,
                    "operations": [
                        {
                            "id": op.id,
                            "method": op.method,
                            "status": op.status,
                            "error": op.error,
                            "result": op.result
                        }
                        for op in batch.operations
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error getting batch status: {str(e)}")
                error = APIError(
                    message=f"Failed to get batch status: {str(e)}",
                    operation="soap.batch.status",
                    details={"batch_id": batch_id}
                )
                return error.to_dict() 