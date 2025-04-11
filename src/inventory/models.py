"""
Inventory management models.

This module defines the core models for managing ad units, placements, and targeting
in the Google Ad Manager system.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum

class AdUnitStatus(str, Enum):
    """Status of an ad unit."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"

class AdUnitType(str, Enum):
    """Type of ad unit."""
    DISPLAY = "DISPLAY"
    VIDEO = "VIDEO"
    NATIVE = "NATIVE"
    CUSTOM = "CUSTOM"

class AdUnit(BaseModel):
    """Ad unit configuration."""
    id: Optional[str] = None
    name: str = Field(..., description="Name of the ad unit")
    code: str = Field(..., description="Ad unit code for rendering")
    parent_id: Optional[str] = Field(None, description="Parent ad unit ID")
    type: AdUnitType = Field(..., description="Type of ad unit")
    size: Dict[str, int] = Field(..., description="Size of the ad unit (width, height)")
    status: AdUnitStatus = Field(default=AdUnitStatus.ACTIVE, description="Status of the ad unit")
    targeting: Dict[str, Any] = Field(default_factory=dict, description="Default targeting for the ad unit")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=datetime.UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=datetime.UTC))

    @validator("size")
    def validate_size(cls, v):
        """Validate ad unit size."""
        if v["width"] <= 0 or v["height"] <= 0:
            raise ValueError("Ad unit dimensions must be positive")
        return v

class PlacementStatus(str, Enum):
    """Status of a placement."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"

class Placement(BaseModel):
    """Placement configuration."""
    id: Optional[str] = None
    name: str = Field(..., description="Name of the placement")
    description: Optional[str] = Field(None, description="Description of the placement")
    ad_unit_ids: List[str] = Field(..., description="List of ad unit IDs in this placement")
    targeting: Dict[str, Any] = Field(default_factory=dict, description="Default targeting for the placement")
    status: PlacementStatus = Field(default=PlacementStatus.ACTIVE, description="Status of the placement")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=datetime.UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=datetime.UTC))

    @validator("ad_unit_ids")
    def validate_ad_unit_ids(cls, v):
        """Validate ad unit IDs."""
        if not v:
            raise ValueError("Placement must contain at least one ad unit")
        return v

class TargetingType(str, Enum):
    """Type of targeting."""
    GEOGRAPHY = "GEOGRAPHY"
    BROWSER = "BROWSER"
    DEVICE = "DEVICE"
    BANDWIDTH = "BANDWIDTH"
    CUSTOM = "CUSTOM"

class TargetingOperator(str, Enum):
    """Targeting operator."""
    IS = "IS"
    IS_NOT = "IS_NOT"
    CONTAINS = "CONTAINS"
    DOES_NOT_CONTAIN = "DOES_NOT_CONTAIN"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"

class TargetingCriteria(BaseModel):
    """Targeting criteria configuration."""
    type: TargetingType
    operator: TargetingOperator
    values: List[str] = Field(..., description="Values to match against")

class TargetingRule(BaseModel):
    """Targeting rule configuration."""
    id: Optional[str] = None
    name: str = Field(..., description="Name of the targeting rule")
    description: Optional[str] = Field(None, description="Description of the targeting rule")
    criteria: List[TargetingCriteria] = Field(..., description="List of targeting criteria")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=datetime.UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=datetime.UTC))

    @validator("criteria")
    def validate_criteria(cls, v):
        """Validate targeting criteria."""
        if not v:
            raise ValueError("Targeting rule must contain at least one criterion")
        return v 