"""
Simplified batch processing system for campaign operations.

This module provides batch operation functionality with proper error handling
and validation, but without unnecessary complexity.
"""

import asyncio
from typing import List, Dict, Any, Callable, Awaitable
from datetime import datetime

from src.config import batch_config
from src.utils.logging import setup_logger
from src.utils.cache import Cache

logger = setup_logger(__name__)
cache = Cache()

class BatchOperation:
    """Batch operation for campaign management."""
    
    def __init__(self, operation_type: str, data: Dict[str, Any]):
        """
        Initialize batch operation.

        Args:
            operation_type: Type of operation (create, update, etc.)
            data: Operation data
        """
        self.operation_type = operation_type
        self.data = data
        self.id = f"{operation_type}_{datetime.now().timestamp()}"
        self.status = "pending"
        self.result = None
        self.error = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert operation to dictionary."""
        return {
            "id": self.id,
            "type": self.operation_type,
            "data": self.data,
            "status": self.status,
            "result": self.result,
            "error": self.error
        }

class BatchProcessor:
    """Process batch operations with proper concurrency control."""
    
    def __init__(self):
        """Initialize batch processor."""
        self.semaphore = asyncio.Semaphore(batch_config.concurrent_limit)
        self.timeout = batch_config.timeout

    async def process_operation(
        self,
        operation: BatchOperation,
        handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
    ) -> None:
        """
        Process a single operation.

        Args:
            operation: Operation to process
            handler: Async function to handle the operation
        """
        try:
            async with self.semaphore:
                operation.result = await asyncio.wait_for(
                    handler(operation.data),
                    timeout=self.timeout
                )
                operation.status = "success"
        except asyncio.TimeoutError:
            operation.status = "timeout"
            operation.error = "Operation timed out"
            logger.error(f"Operation {operation.id} timed out")
        except Exception as e:
            operation.status = "error"
            operation.error = str(e)
            logger.error(f"Error processing operation {operation.id}: {e}")

    async def process_batch(
        self,
        operations: List[BatchOperation],
        handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of operations concurrently.

        Args:
            operations: List of operations to process
            handler: Async function to handle each operation

        Returns:
            List[Dict[str, Any]]: Results of all operations
        """
        if len(operations) > batch_config.max_size:
            raise ValueError(
                f"Batch size {len(operations)} exceeds maximum {batch_config.max_size}"
            )
        
        tasks = [
            self.process_operation(op, handler)
            for op in operations
        ]
        
        await asyncio.gather(*tasks)
        return [op.to_dict() for op in operations]

def create_batch_operation(
    operation_type: str,
    data: Dict[str, Any]
) -> BatchOperation:
    """
    Create a new batch operation.

    Args:
        operation_type: Type of operation
        data: Operation data

    Returns:
        BatchOperation: New operation instance
    """
    return BatchOperation(operation_type, data) 