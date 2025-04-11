"""
Validators for campaign batch operations.

This module provides validation functions to ensure data consistency
and business rule compliance before submitting operations to the batch processor.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from src.campaigns.models import (
    BatchOperation, Order, LineItem, Creative, TargetingRule
)

class ValidationError(Exception):
    """Custom exception for validation errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class BatchValidator:
    """Validates batch operations before processing."""
    
    @staticmethod
    def validate_order(order: Order) -> None:
        """
        Validate order data.
        
        Args:
            order: Order to validate
            
        Raises:
            ValidationError: If validation fails
        """
        # Check date range
        if order.end_datetime <= order.start_datetime:
            raise ValidationError(
                "Order end time must be after start time",
                {"start": order.start_datetime, "end": order.end_datetime}
            )
        
        # Check if start date is in the past
        if order.start_datetime < datetime.utcnow():
            raise ValidationError(
                "Order start time cannot be in the past",
                {"start": order.start_datetime}
            )
        
        # Check maximum duration (e.g., 1 year)
        duration = order.end_datetime - order.start_datetime
        if duration > timedelta(days=365):
            raise ValidationError(
                "Order duration cannot exceed 1 year",
                {"duration_days": duration.days}
            )

    @staticmethod
    def validate_line_item(line_item: LineItem, order: Optional[Order] = None) -> None:
        """
        Validate line item data.
        
        Args:
            line_item: Line item to validate
            order: Optional parent order for additional validation
            
        Raises:
            ValidationError: If validation fails
        """
        # Check date range
        if line_item.end_datetime <= line_item.start_datetime:
            raise ValidationError(
                "Line item end time must be after start time",
                {"start": line_item.start_datetime, "end": line_item.end_datetime}
            )
        
        # Validate against parent order if provided
        if order:
            if line_item.start_datetime < order.start_datetime:
                raise ValidationError(
                    "Line item start time cannot be before order start time",
                    {
                        "line_item_start": line_item.start_datetime,
                        "order_start": order.start_datetime
                    }
                )
            
            if line_item.end_datetime > order.end_datetime:
                raise ValidationError(
                    "Line item end time cannot be after order end time",
                    {
                        "line_item_end": line_item.end_datetime,
                        "order_end": order.end_datetime
                    }
                )

    @staticmethod
    def validate_creative(creative: Creative) -> None:
        """
        Validate creative data.
        
        Args:
            creative: Creative to validate
            
        Raises:
            ValidationError: If validation fails
        """
        # Check size constraints
        if creative.size["width"] <= 0 or creative.size["height"] <= 0:
            raise ValidationError(
                "Creative dimensions must be positive",
                {"size": creative.size}
            )
        
        # Check if either preview URL or snippet is provided
        if not creative.preview_url and not creative.snippet:
            raise ValidationError(
                "Creative must have either preview URL or snippet"
            )

    @staticmethod
    def validate_targeting_rule(rule: TargetingRule) -> None:
        """
        Validate targeting rule data.
        
        Args:
            rule: Targeting rule to validate
            
        Raises:
            ValidationError: If validation fails
        """
        valid_types = {"GEO", "BROWSER", "DEVICE", "CUSTOM"}
        if rule.type not in valid_types:
            raise ValidationError(
                f"Invalid targeting rule type: {rule.type}",
                {"valid_types": list(valid_types)}
            )
        
        if not rule.criteria:
            raise ValidationError("Targeting criteria cannot be empty")

    @classmethod
    def validate_batch_operation(cls, operation: BatchOperation) -> None:
        """
        Validate a single batch operation.
        
        Args:
            operation: Operation to validate
            
        Raises:
            ValidationError: If validation fails
        """
        valid_types = {"CREATE", "UPDATE", "DELETE"}
        if operation.operation_type not in valid_types:
            raise ValidationError(
                f"Invalid operation type: {operation.operation_type}",
                {"valid_types": list(valid_types)}
            )
        
        valid_entities = {"ORDER", "LINE_ITEM", "CREATIVE"}
        if operation.entity_type not in valid_entities:
            raise ValidationError(
                f"Invalid entity type: {operation.entity_type}",
                {"valid_entities": list(valid_entities)}
            )
        
        # Validate entity-specific data
        if operation.entity_type == "ORDER":
            cls.validate_order(Order(**operation.data))
        elif operation.entity_type == "LINE_ITEM":
            cls.validate_line_item(LineItem(**operation.data))
        elif operation.entity_type == "CREATIVE":
            cls.validate_creative(Creative(**operation.data))

    @classmethod
    def validate_batch(cls, operations: List[BatchOperation]) -> None:
        """
        Validate a batch of operations.
        
        Args:
            operations: List of operations to validate
            
        Raises:
            ValidationError: If validation fails
        """
        if not operations:
            raise ValidationError("Batch cannot be empty")
        
        # Track orders and line items for cross-validation
        orders: Dict[str, Order] = {}
        line_items: List[LineItem] = []
        
        # First pass: validate individual operations and collect orders
        for operation in operations:
            cls.validate_batch_operation(operation)
            
            if operation.entity_type == "ORDER" and operation.operation_type == "CREATE":
                order = Order(**operation.data)
                orders[operation.operation_id] = order
            elif operation.entity_type == "LINE_ITEM" and operation.operation_type == "CREATE":
                line_items.append((operation, LineItem(**operation.data)))
        
        # Second pass: validate line items against their orders
        for operation, line_item in line_items:
            order_id = line_item.order_id
            if order_id in orders:
                cls.validate_line_item(line_item, orders[order_id]) 