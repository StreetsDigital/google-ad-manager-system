"""
Campaign operation models for batch processing.

This module defines the core models used for campaign operations in the batch processing system.
Models are used to validate and structure data before processing through the SOAP client.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class LineItem(BaseModel):
    """Line item configuration for campaign."""
    id: Optional[str] = None
    name: str = Field(..., description="Name of the line item")
    order_id: str = Field(..., description="ID of the parent order")
    start_datetime: datetime = Field(..., description="Start time of the line item")
    end_datetime: datetime = Field(..., description="End time of the line item")
    targeting: Dict[str, Any] = Field(default_factory=dict, description="Targeting criteria")
    creative_ids: List[str] = Field(default_factory=list, description="Associated creative IDs")
    status: str = Field(default="DRAFT", description="Status of the line item")

class Order(BaseModel):
    """Campaign order configuration."""
    id: Optional[str] = None
    name: str = Field(..., description="Name of the order")
    advertiser_id: str = Field(..., description="ID of the advertiser")
    trafficker_id: Optional[str] = Field(None, description="ID of the trafficker")
    status: str = Field(default="DRAFT", description="Status of the order")
    start_datetime: datetime = Field(..., description="Start time of the order")
    end_datetime: datetime = Field(..., description="End time of the order")

class Creative(BaseModel):
    """Creative asset configuration."""
    id: Optional[str] = None
    name: str = Field(..., description="Name of the creative")
    advertiser_id: str = Field(..., description="ID of the advertiser")
    size: Dict[str, int] = Field(..., description="Size of the creative (width, height)")
    preview_url: Optional[str] = Field(None, description="Preview URL for the creative")
    snippet: Optional[str] = Field(None, description="HTML snippet for the creative")
    status: str = Field(default="DRAFT", description="Status of the creative")

class TargetingRule(BaseModel):
    """Targeting rule configuration."""
    id: Optional[str] = None
    name: str = Field(..., description="Name of the targeting rule")
    type: str = Field(..., description="Type of targeting (GEO, BROWSER, etc)")
    criteria: Dict[str, Any] = Field(..., description="Targeting criteria")
    description: Optional[str] = Field(None, description="Description of the targeting rule")

class BatchOperation(BaseModel):
    """Represents a single operation in a batch."""
    
    operation_id: str
    operation_type: str  # CREATE, UPDATE, DELETE
    entity_type: str    # ORDER, LINE_ITEM, CREATIVE
    data: Dict[str, Any]
    status: str = "PENDING"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    error: Optional[str] = None 