"""
Campaign operation processors.

This module provides processors for handling different types of campaign operations,
preparing them for batch processing and handling their results.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

from src.campaigns.models import (
    BatchOperation, Order, LineItem, Creative, TargetingRule
)
from src.campaigns.batch.validators import BatchValidator, ValidationError

# Configure logging
logger = logging.getLogger(__name__)

class OrderProcessor:
    """Processor for order operations."""
    
    @staticmethod
    def prepare_create(order: Order) -> BatchOperation:
        """
        Prepare a create order operation.
        
        Args:
            order: Order to create
            
        Returns:
            BatchOperation ready for processing
        """
        return BatchOperation(
            operation_id=f"create_order_{uuid4().hex[:8]}",
            operation_type="CREATE",
            entity_type="ORDER",
            data=order.dict()
        )
    
    @staticmethod
    def prepare_update(order_id: str, updates: Dict[str, Any]) -> BatchOperation:
        """
        Prepare an update order operation.
        
        Args:
            order_id: ID of order to update
            updates: Fields to update
            
        Returns:
            BatchOperation ready for processing
        """
        return BatchOperation(
            operation_id=f"update_order_{uuid4().hex[:8]}",
            operation_type="UPDATE",
            entity_type="ORDER",
            data={"id": order_id, **updates}
        )

class LineItemProcessor:
    """Processor for line item operations."""
    
    @staticmethod
    def prepare_create(line_item: LineItem) -> BatchOperation:
        """
        Prepare a create line item operation.
        
        Args:
            line_item: Line item to create
            
        Returns:
            BatchOperation ready for processing
        """
        return BatchOperation(
            operation_id=f"create_lineitem_{uuid4().hex[:8]}",
            operation_type="CREATE",
            entity_type="LINE_ITEM",
            data=line_item.dict()
        )
    
    @staticmethod
    def prepare_update(line_item_id: str, updates: Dict[str, Any]) -> BatchOperation:
        """
        Prepare an update line item operation.
        
        Args:
            line_item_id: ID of line item to update
            updates: Fields to update
            
        Returns:
            BatchOperation ready for processing
        """
        return BatchOperation(
            operation_id=f"update_lineitem_{uuid4().hex[:8]}",
            operation_type="UPDATE",
            entity_type="LINE_ITEM",
            data={"id": line_item_id, **updates}
        )

class CreativeProcessor:
    """Processor for creative operations."""
    
    @staticmethod
    def prepare_create(creative: Creative) -> BatchOperation:
        """
        Prepare a create creative operation.
        
        Args:
            creative: Creative to create
            
        Returns:
            BatchOperation ready for processing
        """
        return BatchOperation(
            operation_id=f"create_creative_{uuid4().hex[:8]}",
            operation_type="CREATE",
            entity_type="CREATIVE",
            data=creative.dict()
        )
    
    @staticmethod
    def prepare_update(creative_id: str, updates: Dict[str, Any]) -> BatchOperation:
        """
        Prepare an update creative operation.
        
        Args:
            creative_id: ID of creative to update
            updates: Fields to update
            
        Returns:
            BatchOperation ready for processing
        """
        return BatchOperation(
            operation_id=f"update_creative_{uuid4().hex[:8]}",
            operation_type="UPDATE",
            entity_type="CREATIVE",
            data={"id": creative_id, **updates}
        )

class CampaignProcessor:
    """High-level processor for campaign operations."""
    
    def __init__(self):
        """Initialize processors."""
        self.order_processor = OrderProcessor()
        self.line_item_processor = LineItemProcessor()
        self.creative_processor = CreativeProcessor()
        self.validator = BatchValidator()
    
    def prepare_campaign_create(
        self,
        order: Order,
        line_items: List[LineItem],
        creatives: Optional[List[Creative]] = None
    ) -> List[BatchOperation]:
        """
        Prepare operations for creating a complete campaign.
        
        Args:
            order: Campaign order
            line_items: Line items for the campaign
            creatives: Optional creatives to create
            
        Returns:
            List of operations ready for batch processing
        """
        operations = []
        
        # Create order operation
        order_op = self.order_processor.prepare_create(order)
        operations.append(order_op)
        
        # Create line item operations
        for line_item in line_items:
            line_item_op = self.line_item_processor.prepare_create(line_item)
            operations.append(line_item_op)
        
        # Create creative operations if provided
        if creatives:
            for creative in creatives:
                creative_op = self.creative_processor.prepare_create(creative)
                operations.append(creative_op)
        
        # Validate the complete batch
        self.validator.validate_batch(operations)
        
        return operations
    
    def prepare_campaign_update(
        self,
        order_updates: Optional[Dict[str, Any]] = None,
        line_item_updates: Optional[Dict[str, Dict[str, Any]]] = None,
        creative_updates: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[BatchOperation]:
        """
        Prepare operations for updating campaign components.
        
        Args:
            order_updates: Updates for the order
            line_item_updates: Updates for line items, keyed by ID
            creative_updates: Updates for creatives, keyed by ID
            
        Returns:
            List of operations ready for batch processing
        """
        operations = []
        
        # Add order update if provided
        if order_updates:
            order_op = self.order_processor.prepare_update(
                order_updates.pop("id"),
                order_updates
            )
            operations.append(order_op)
        
        # Add line item updates
        if line_item_updates:
            for line_item_id, updates in line_item_updates.items():
                line_item_op = self.line_item_processor.prepare_update(
                    line_item_id,
                    updates
                )
                operations.append(line_item_op)
        
        # Add creative updates
        if creative_updates:
            for creative_id, updates in creative_updates.items():
                creative_op = self.creative_processor.prepare_update(
                    creative_id,
                    updates
                )
                operations.append(creative_op)
        
        # Validate the complete batch
        self.validator.validate_batch(operations)
        
        return operations 