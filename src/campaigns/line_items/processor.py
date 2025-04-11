"""
Line item processing module with retry capabilities.

This module handles the processing of line items, including validation of relationships
with orders and creatives, and ensuring proper date constraints are met.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone
from functools import wraps

from src.campaigns.models import LineItem, Order, Creative
from src.tools.soap_tools import SoapToolAdapter, RetryConfig
from src.campaigns.line_items.connection_pool import ConnectionPool
from src.auth.errors import (
    RetryStrategy,
    NetworkError,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError,
    retryable
)

logger = logging.getLogger(__name__)

def with_rate_limit(max_requests: int = 3, window_seconds: float = 1.0):
    """
    Rate limiting decorator for class methods.
    
    Args:
        max_requests: Maximum number of requests allowed in the window
        window_seconds: Time window in seconds
        
    Returns:
        Decorated method with rate limiting
    """
    def decorator(func):
        # Store timestamps in class instance to handle multiple instances
        timestamps_attr = f"_{func.__name__}_timestamps"
        
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Initialize timestamps list if not exists
            if not hasattr(self, timestamps_attr):
                setattr(self, timestamps_attr, [])
            
            timestamps = getattr(self, timestamps_attr)
            now = datetime.now()
            
            # Remove old timestamps
            while timestamps and (now - timestamps[0]).total_seconds() > window_seconds:
                timestamps.pop(0)
            
            # Check if we're over the limit
            if len(timestamps) >= max_requests:
                wait_time = window_seconds - (now - timestamps[0]).total_seconds()
                if wait_time > 0:
                    logger.warning(f"Rate limit reached for {func.__name__}, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    # Clear timestamps after waiting
                    timestamps.clear()
            
            # Add current timestamp
            timestamps.append(now)
            
            # Execute the method
            logger.debug(f"Executing rate-limited call to {func.__name__}")
            return await func(self, *args, **kwargs)
        
        return wrapper
    return decorator

class LineItemProcessor:
    """Handles processing and validation of line items with retry capabilities."""

    def __init__(
        self, 
        connection_pool: ConnectionPool,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize the processor.
        
        Args:
            connection_pool: Connection pool for managing SOAP connections
            retry_config: Optional retry configuration. If not provided, uses defaults
        """
        self.connection_pool = connection_pool
        self.retry_config = retry_config or RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=True
        )

    def _build_response(self, results=None, errors=None, status=None):
        """Build a standardized response format.
        
        Args:
            results (List[Dict]): List of successful results
            errors (List[Dict]): List of errors
            status (str): Status override. If not provided, will be determined by results/errors
            
        Returns:
            Dict: Standardized response with data and status
        """
        if results is None:
            results = []
        if errors is None:
            errors = []
        
        if status is None:
            if len(errors) > 0:
                if len(results) > 0:
                    status = "partial"
                else:
                    status = "error"
            else:
                status = "success"
            
        return {
            "status": status,
            "data": {
                "results": results,
                "errors": errors
            }
        }

    @retryable()
    async def _fetch_order(self, order_id: str) -> Dict[str, Any]:
        """Fetch order details with retry capability."""
        async with self.connection_pool.get_connection() as conn:
            return await conn.get_order(order_id)

    @retryable()
    async def _fetch_creatives(self, creative_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch creative details with retry capability."""
        async with self.connection_pool.get_connection() as conn:
            return await conn.get_creatives(creative_ids)

    @retryable()
    async def _fetch_targeting(self, targeting_id: str) -> Dict[str, Any]:
        """Fetch targeting details with retry capability."""
        async with self.connection_pool.get_connection() as conn:
            return await conn.get_targeting(targeting_id)

    @retryable()
    async def _create_line_item(self, line_item: Dict[str, Any]) -> Dict[str, Any]:
        """Create a line item with retry capability."""
        async with self.connection_pool.get_connection() as conn:
            return await conn.create_line_item(line_item)

    async def _validate_order_constraints(
        self, 
        line_item: Dict[str, Any],
        cached_order: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[str], Optional[Dict[str, Any]]]:
        """Validate order constraints with error handling."""
        errors = []
        order = None
        
        try:
            order = cached_order or await self._fetch_order(line_item["orderId"])
            
            if order["status"] != "approved":
                errors.append(f"Order {order['id']} is not approved")
            
            if line_item["startDate"] < order["startDate"]:
                errors.append("Line item start date cannot be before order start date")
            
            if line_item["endDate"] > order["endDate"]:
                errors.append("Line item end date cannot be after order end date")
                
        except (NetworkError, RateLimitError, ServiceUnavailableError, TimeoutError) as e:
            logger.error(f"Error validating order constraints: {str(e)}")
            errors.append(f"Failed to validate order: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error validating order constraints: {str(e)}")
            errors.append(f"Unexpected error validating order: {str(e)}")
            
        return errors, order

    async def _validate_creatives(
        self, 
        line_item: Dict[str, Any]
    ) -> List[str]:
        """Validate creatives with error handling."""
        errors = []
        
        try:
            creatives = await self._fetch_creatives(line_item["creativeIds"])
            
            for creative in creatives:
                if not creative["active"]:
                    errors.append(f"Creative {creative['id']} is not active")
                if creative["size"] != line_item["size"]:
                    errors.append(f"Creative {creative['id']} size does not match line item size")
                    
        except (NetworkError, RateLimitError, ServiceUnavailableError, TimeoutError) as e:
            logger.error(f"Error validating creatives: {str(e)}")
            errors.append(f"Failed to validate creatives: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error validating creatives: {str(e)}")
            errors.append(f"Unexpected error validating creatives: {str(e)}")
            
        return errors

    async def _validate_targeting(
        self, 
        line_item: Dict[str, Any]
    ) -> List[str]:
        """Validate targeting rules with error handling."""
        errors = []
        
        try:
            targeting = await self._fetch_targeting(line_item["targetingId"])
            
            if not targeting["rules"]:
                errors.append("Targeting must have at least one rule")
            
            for rule in targeting["rules"]:
                if not rule.get("criteria"):
                    errors.append(f"Targeting rule {rule['id']} must have criteria")
                    
        except (NetworkError, RateLimitError, ServiceUnavailableError, TimeoutError) as e:
            logger.error(f"Error validating targeting: {str(e)}")
            errors.append(f"Failed to validate targeting: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error validating targeting: {str(e)}")
            errors.append(f"Unexpected error validating targeting: {str(e)}")
            
        return errors

    async def validate_line_item(
        self, 
        line_item: LineItem, 
        cached_order: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate a line item and its relationships.
        
        Args:
            line_item: The line item to validate
            cached_order: Optional cached order to validate against
            
        Returns:
            Dict containing validation status and any errors
        """
        errors = []
        
        # Validate order relationship
        order_errors, order = await self._validate_order_constraints(
            line_item.dict(),
            cached_order
        )
        errors.extend(order_errors)
        
        # Validate creative relationships if present
        if line_item.creative_ids:
            creative_errors = await self._validate_creatives(line_item.dict())
            errors.extend(creative_errors)

        # Validate targeting rules if present
        if line_item.targeting:
            targeting_errors = await self._validate_targeting(line_item.dict())
            errors.extend(targeting_errors)

        return self._build_response(
            results=None,
            errors=errors if errors else None
        )

    async def create_line_items(self, line_items: List[LineItem]) -> Dict[str, Any]:
        """
        Create multiple line items with retry capability.
        
        Args:
            line_items: List of line items to create
            
        Returns:
            Dict containing creation status and results
        """
        if not line_items:
            return self._build_response(
                errors=["No line items provided"]
            )

        validation_errors = {}
        valid_line_items = []
        orders_cache = {}
        
        # Validate all line items first
        for line_item in line_items:
            item_errors = []
            
            try:
                # Get cached order or fetch new one
                order = orders_cache.get(line_item.order_id)
                order_errors, order = await self._validate_order_constraints(
                    line_item.dict(), 
                    order
                )
                if order:
                    orders_cache[line_item.order_id] = order
                item_errors.extend(order_errors)
                
                # Validate creatives
                creative_errors = await self._validate_creatives(line_item.dict())
                item_errors.extend(creative_errors)
                
                # Validate targeting
                targeting_errors = await self._validate_targeting(line_item.dict())
                item_errors.extend(targeting_errors)
                
            except (NetworkError, RateLimitError, ServiceUnavailableError, TimeoutError) as e:
                logger.error(f"Error during validation: {str(e)}")
                item_errors.append(str(e))
                
            if item_errors:
                validation_errors[line_item.id] = item_errors
            else:
                valid_line_items.append(line_item)

        if not valid_line_items:
            return self._build_response(
                errors=["All line items failed validation"]
            )

        # Create valid line items concurrently
        results = []
        errors = []
        
        tasks = [
            asyncio.create_task(self._create_line_item(item.dict()))
            for item in valid_line_items
        ]
        
        try:
            completed, pending = await asyncio.wait(
                tasks,
                timeout=self.retry_config.max_delay * self.retry_config.max_attempts
            )
            
            for task in completed:
                try:
                    result = await task
                    if result["status"] == "success":
                        results.append(result["line_item"])
                    else:
                        errors.append({
                            "error": result.get("message", "Unknown error")
                        })
                except Exception as e:
                    errors.append({"error": str(e)})
            
            for task in pending:
                task.cancel()
                errors.append({"error": "Operation timed out"})
                
        except Exception as e:
            logger.error(f"Error in batch creation: {str(e)}")
            return self._build_response(
                errors=[str(e)]
            )

        # Determine final status
        if len(errors) == len(line_items):
            status = "failure"
            summary = f"All {len(line_items)} line items failed to create"
        elif errors:
            status = "partial"
            summary = f"{len(errors)} of {len(line_items)} line items failed to create"
        else:
            status = "success"
            summary = f"Successfully created {len(results)} line items"

        return self._build_response(
            results=results,
            errors=[error["error"] for error in errors],
            status=status
        )

    @with_rate_limit()
    async def update_line_item(self, line_item_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing line item.
        
        Args:
            line_item_id: ID of the line item to update
            updates: Dictionary of fields to update
            
        Returns:
            Dict containing update status and result
        """
        try:
            result = await self.connection_pool.execute_request(
                method="updateLineItem",
                line_item_id=line_item_id,
                line_item=updates
            )
            
            if result.get("status") == "error":
                return self._build_response(
                    errors=[result.get("message")]
                )
                
            return self._build_response(
                results=[result["line_item"]]
            )

        except Exception as e:
            logger.error(f"Error updating line item: {e}", exc_info=True)
            return self._build_response(
                errors=[f"Failed to update line item: {str(e)}"]
            )

    async def update_line_items(
        self, 
        updates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Update multiple line items in a batch.
        
        Args:
            updates: List of dictionaries containing line_item_id and updates
            
        Returns:
            Dict containing update status and results
        """
        if len(updates) > self.retry_config.max_attempts:
            return self._build_response(
                errors=f"Batch size exceeds maximum of {self.retry_config.max_attempts}"
            )
            
        results = []
        success_count = 0
        error_count = 0
        
        # Create tasks for concurrent execution
        tasks = []
        for update in updates:
            line_item_id = update.get("line_item_id")
            update_data = update.get("updates", {})
            
            if not line_item_id:
                error_count += 1
                results.append(self._build_response(
                    errors=["Missing line_item_id in update data"]
                ))
                continue
                
            tasks.append(asyncio.create_task(
                self.update_line_item(line_item_id, update_data)
            ))
        
        try:
            # Wait for all tasks with timeout
            completed, pending = await asyncio.wait(
                tasks,
                timeout=self.retry_config.max_delay * self.retry_config.max_attempts
            )
            
            # Handle completed tasks
            for task in completed:
                try:
                    result = await task
                    results.append(result)
                    if result["status"] == "success":
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Task error: {e}", exc_info=True)
                    error_count += 1
                    results.append(self._build_response(
                        errors=[f"Operation failed: {str(e)}"]
                    ))
            
            # Handle pending (timed out) tasks
            for task in pending:
                task.cancel()
                error_count += 1
                results.append(self._build_response(
                    errors=["Operation timed out"]
                ))
        
        except Exception as e:
            logger.error(f"Batch operation error: {e}", exc_info=True)
            return self._build_response(
                errors=[f"Batch operation failed: {str(e)}"]
            )
        
        return self._build_response(
            results=results,
            status="success" if error_count == 0 else "partial" if success_count > 0 else "error",
            errors=[error["error"] for error in errors],
            summary={
                "total": len(updates),
                "success": success_count,
                "error": error_count
            }
        )

    async def get_line_items_by_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get all line items for an order.
        
        Args:
            order_id: ID of the order
            
        Returns:
            Dict containing list of line items
        """
        try:
            result = await self.connection_pool.execute_request(
                method="getLineItemsByOrder",
                order_id=order_id
            )
            
            return self._build_response(
                results=result if result.get("status") == "success" else None,
                errors=[result.get("message")] if result.get("status") == "error" else None
            )

        except Exception as e:
            logger.error(f"Error fetching line items: {e}", exc_info=True)
            return self._build_response(
                errors=[f"Failed to fetch line items: {str(e)}"]
            )

    def get_processor_stats(self) -> Dict[str, Any]:
        """Get statistics about the processor's operations."""
        pool_stats = self.connection_pool.get_pool_stats()
        return {
            "connection_pool": pool_stats,
            "max_attempts": self.retry_config.max_attempts,
            "max_delay": self.retry_config.max_delay
        } 