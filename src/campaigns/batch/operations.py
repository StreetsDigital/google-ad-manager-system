"""
Batch operations handler for campaign management.

This module provides the core functionality for processing campaign operations in batches,
integrating with the SOAP client's batch processing capabilities.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import asyncio
from uuid import uuid4

from src.tools.soap_tools import SoapToolAdapter
from src.campaigns.models import BatchOperation, Order, LineItem, Creative, TargetingRule

# Configure logging
logger = logging.getLogger(__name__)

class CampaignBatchProcessor:
    """Handles batch operations for campaign management."""
    
    def __init__(self, adapter: SoapToolAdapter):
        """Initialize the processor with a SOAP tool adapter."""
        self.adapter = adapter
        self._active_batches: Dict[str, List[BatchOperation]] = {}

    async def _prepare_operation(self, operation: BatchOperation) -> Dict[str, Any]:
        """Prepare a single operation for batch submission."""
        # Convert entity type to proper method name format (e.g., ORDER -> Orders)
        entity_type = operation.entity_type.capitalize()
        method = f"create{entity_type}s"
        
        return {
            "id": operation.operation_id,
            "method": method,
            "params": {
                entity_type.lower() + "s": [operation.data]
            }
        }

    async def submit_batch(self, operations: List[BatchOperation]) -> Dict[str, Any]:
        """Submit a batch of operations."""
        try:
            # Get batch tool from registry
            batch_tool = await self.adapter.registry.get_tool("batch")
            
            # Prepare all operations
            prepared_ops = []
            for op in operations:
                prepared = await self._prepare_operation(op)
                prepared_ops.append(prepared)

            # Submit batch
            result = await batch_tool(operations=prepared_ops)
            
            # Store operations for status tracking if accepted
            if result.get("status") == "accepted":
                self._active_batches[result["batch_id"]] = operations
                result["operation_count"] = len(operations)
            
            return result

        except Exception as e:
            logger.error(f"Error submitting batch: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to submit batch: {str(e)}"
            }

    async def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """Get the status of a batch operation."""
        if batch_id not in self._active_batches:
            return {
                "status": "error",
                "message": f"Batch {batch_id} not found"
            }

        try:
            status_tool = await self.adapter.registry.get_tool("status")
            result = await status_tool(batch_id=batch_id)
            
            # Update operation statuses
            if "operations" in result:
                operations = self._active_batches[batch_id]
                for op_result in result["operations"]:
                    for operation in operations:
                        if operation.operation_id == op_result["id"]:
                            operation.status = op_result["status"]
                            operation.updated_at = datetime.now(timezone.utc)
                            if "error" in op_result:
                                operation.error = op_result["error"]
                            break

            return result

        except Exception as e:
            logger.error(f"Error getting batch status: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to get batch status: {str(e)}"
            }

    async def wait_for_batch(self, batch_id: str, timeout: int = 300, check_interval: int = 5) -> Dict[str, Any]:
        """Wait for a batch operation to complete."""
        if batch_id not in self._active_batches:
            return {
                "status": "error",
                "message": f"Batch {batch_id} not found"
            }

        start_time = datetime.now(timezone.utc)
        while True:
            if (datetime.now(timezone.utc) - start_time).total_seconds() > timeout:
                return {
                    "status": "timeout",
                    "message": f"Batch {batch_id} timed out after {timeout} seconds"
                }

            status = await self.get_batch_status(batch_id)
            if status["status"] in ["completed", "error"]:
                return status

            # Wait before checking again
            await asyncio.sleep(check_interval) 