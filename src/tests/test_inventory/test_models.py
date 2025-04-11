"""Tests for inventory management models."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.inventory.models import (
    AdUnit, AdUnitStatus, AdUnitType,
    Placement, PlacementStatus,
    TargetingRule, TargetingType, TargetingOperator, TargetingCriteria
)

@pytest.fixture
def valid_ad_unit():
    """Create a valid ad unit for testing."""
    return AdUnit(
        name="Homepage Banner",
        code="div-gpt-ad-123456789",
        type=AdUnitType.DISPLAY,
        size={"width": 300, "height": 250},
        targeting={"genre": "sports"}
    )

@pytest.fixture
def valid_placement(valid_ad_unit):
    """Create a valid placement for testing."""
    return Placement(
        name="Sports Section",
        description="All sports section ad units",
        ad_unit_ids=["unit1", "unit2"],
        targeting={"genre": "sports"}
    )

@pytest.fixture
def valid_targeting_rule():
    """Create a valid targeting rule for testing."""
    return TargetingRule(
        name="US Desktop Users",
        description="Target users in US on desktop devices",
        criteria=[
            TargetingCriteria(
                type=TargetingType.GEOGRAPHY,
                operator=TargetingOperator.IS,
                values=["US"]
            ),
            TargetingCriteria(
                type=TargetingType.DEVICE,
                operator=TargetingOperator.IS,
                values=["DESKTOP"]
            )
        ]
    )

class TestAdUnit:
    """Test cases for AdUnit model."""

    def test_valid_ad_unit(self, valid_ad_unit):
        """Test creating a valid ad unit."""
        assert valid_ad_unit.name == "Homepage Banner"
        assert valid_ad_unit.type == AdUnitType.DISPLAY
        assert valid_ad_unit.status == AdUnitStatus.ACTIVE
        assert valid_ad_unit.size == {"width": 300, "height": 250}

    def test_invalid_size(self):
        """Test validation of invalid ad unit size."""
        with pytest.raises(ValidationError) as exc_info:
            AdUnit(
                name="Invalid Unit",
                code="div-gpt-ad-123456789",
                type=AdUnitType.DISPLAY,
                size={"width": 0, "height": 250}
            )
        assert "Ad unit dimensions must be positive" in str(exc_info.value)

    def test_timestamps(self, valid_ad_unit):
        """Test automatic timestamp generation."""
        assert isinstance(valid_ad_unit.created_at, datetime)
        assert isinstance(valid_ad_unit.updated_at, datetime)
        assert valid_ad_unit.created_at.tzinfo == timezone.UTC
        assert valid_ad_unit.updated_at.tzinfo == timezone.UTC

class TestPlacement:
    """Test cases for Placement model."""

    def test_valid_placement(self, valid_placement):
        """Test creating a valid placement."""
        assert valid_placement.name == "Sports Section"
        assert valid_placement.status == PlacementStatus.ACTIVE
        assert len(valid_placement.ad_unit_ids) == 2

    def test_empty_ad_units(self):
        """Test validation of placement with no ad units."""
        with pytest.raises(ValidationError) as exc_info:
            Placement(
                name="Invalid Placement",
                ad_unit_ids=[]
            )
        assert "Placement must contain at least one ad unit" in str(exc_info.value)

    def test_timestamps(self, valid_placement):
        """Test automatic timestamp generation."""
        assert isinstance(valid_placement.created_at, datetime)
        assert isinstance(valid_placement.updated_at, datetime)
        assert valid_placement.created_at.tzinfo == timezone.UTC
        assert valid_placement.updated_at.tzinfo == timezone.UTC

class TestTargetingRule:
    """Test cases for TargetingRule model."""

    def test_valid_targeting_rule(self, valid_targeting_rule):
        """Test creating a valid targeting rule."""
        assert valid_targeting_rule.name == "US Desktop Users"
        assert len(valid_targeting_rule.criteria) == 2
        assert valid_targeting_rule.criteria[0].type == TargetingType.GEOGRAPHY
        assert valid_targeting_rule.criteria[1].type == TargetingType.DEVICE

    def test_empty_criteria(self):
        """Test validation of targeting rule with no criteria."""
        with pytest.raises(ValidationError) as exc_info:
            TargetingRule(
                name="Invalid Rule",
                criteria=[]
            )
        assert "Targeting rule must contain at least one criterion" in str(exc_info.value)

    def test_timestamps(self, valid_targeting_rule):
        """Test automatic timestamp generation."""
        assert isinstance(valid_targeting_rule.created_at, datetime)
        assert isinstance(valid_targeting_rule.updated_at, datetime)
        assert valid_targeting_rule.created_at.tzinfo == timezone.UTC
        assert valid_targeting_rule.updated_at.tzinfo == timezone.UTC

class TestTargetingCriteria:
    """Test cases for TargetingCriteria model."""

    def test_valid_criteria(self):
        """Test creating valid targeting criteria."""
        criteria = TargetingCriteria(
            type=TargetingType.GEOGRAPHY,
            operator=TargetingOperator.IS,
            values=["US", "CA"]
        )
        assert criteria.type == TargetingType.GEOGRAPHY
        assert criteria.operator == TargetingOperator.IS
        assert len(criteria.values) == 2

    def test_empty_values(self):
        """Test validation of criteria with no values."""
        with pytest.raises(ValidationError):
            TargetingCriteria(
                type=TargetingType.GEOGRAPHY,
                operator=TargetingOperator.IS,
                values=[]
            ) 