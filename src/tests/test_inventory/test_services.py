"""Tests for inventory management services."""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone

from src.inventory.models import (
    AdUnit, AdUnitStatus, AdUnitType,
    Placement, PlacementStatus,
    TargetingRule, TargetingType, TargetingOperator, TargetingCriteria
)
from src.inventory.services import AdUnitService, PlacementService, TargetingService
from src.campaigns.line_items.connection_pool import ConnectionPool

@pytest.fixture
def mock_connection():
    """Create a mock connection."""
    connection = AsyncMock()
    
    # Mock successful responses
    connection.create_ad_unit.return_value = {
        "id": "unit1",
        "createdAt": datetime.now(timezone.UTC).isoformat(),
        "updatedAt": datetime.now(timezone.UTC).isoformat()
    }
    connection.create_placement.return_value = {
        "id": "placement1",
        "createdAt": datetime.now(timezone.UTC).isoformat(),
        "updatedAt": datetime.now(timezone.UTC).isoformat()
    }
    connection.create_targeting_rule.return_value = {
        "id": "rule1",
        "createdAt": datetime.now(timezone.UTC).isoformat(),
        "updatedAt": datetime.now(timezone.UTC).isoformat()
    }
    
    return connection

@pytest.fixture
def mock_pool(mock_connection):
    """Create a mock connection pool."""
    pool = Mock(spec=ConnectionPool)
    pool.get_connection.return_value.__aenter__.return_value = mock_connection
    pool.get_connection.return_value.__aexit__.return_value = None
    return pool

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
def valid_placement():
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

class TestAdUnitService:
    """Test cases for AdUnitService."""

    @pytest.mark.asyncio
    async def test_create_ad_unit(self, mock_pool, valid_ad_unit, mock_connection):
        """Test creating an ad unit."""
        service = AdUnitService(mock_pool)
        result = await service.create_ad_unit(valid_ad_unit)
        
        assert result.id == "unit1"
        mock_connection.create_ad_unit.assert_called_once_with({
            "name": valid_ad_unit.name,
            "code": valid_ad_unit.code,
            "parentId": valid_ad_unit.parent_id,
            "type": valid_ad_unit.type.value,
            "size": valid_ad_unit.size,
            "status": valid_ad_unit.status.value,
            "targeting": valid_ad_unit.targeting
        })

    @pytest.mark.asyncio
    async def test_get_ad_unit(self, mock_pool, mock_connection):
        """Test getting an ad unit."""
        mock_connection.get_ad_unit.return_value = {
            "id": "unit1",
            "name": "Homepage Banner",
            "code": "div-gpt-ad-123456789",
            "type": "DISPLAY",
            "size": {"width": 300, "height": 250},
            "status": "ACTIVE",
            "targeting": {"genre": "sports"},
            "createdAt": datetime.now(timezone.UTC).isoformat(),
            "updatedAt": datetime.now(timezone.UTC).isoformat()
        }
        
        service = AdUnitService(mock_pool)
        result = await service.get_ad_unit("unit1")
        
        assert result.id == "unit1"
        assert result.name == "Homepage Banner"
        assert result.type == AdUnitType.DISPLAY
        mock_connection.get_ad_unit.assert_called_once_with("unit1")

class TestPlacementService:
    """Test cases for PlacementService."""

    @pytest.mark.asyncio
    async def test_create_placement(self, mock_pool, valid_placement, mock_connection):
        """Test creating a placement."""
        service = PlacementService(mock_pool)
        result = await service.create_placement(valid_placement)
        
        assert result.id == "placement1"
        mock_connection.create_placement.assert_called_once_with({
            "name": valid_placement.name,
            "description": valid_placement.description,
            "adUnitIds": valid_placement.ad_unit_ids,
            "targeting": valid_placement.targeting,
            "status": valid_placement.status.value
        })

    @pytest.mark.asyncio
    async def test_get_placement(self, mock_pool, mock_connection):
        """Test getting a placement."""
        mock_connection.get_placement.return_value = {
            "id": "placement1",
            "name": "Sports Section",
            "description": "All sports section ad units",
            "adUnitIds": ["unit1", "unit2"],
            "targeting": {"genre": "sports"},
            "status": "ACTIVE",
            "createdAt": datetime.now(timezone.UTC).isoformat(),
            "updatedAt": datetime.now(timezone.UTC).isoformat()
        }
        
        service = PlacementService(mock_pool)
        result = await service.get_placement("placement1")
        
        assert result.id == "placement1"
        assert result.name == "Sports Section"
        assert len(result.ad_unit_ids) == 2
        mock_connection.get_placement.assert_called_once_with("placement1")

class TestTargetingService:
    """Test cases for TargetingService."""

    @pytest.mark.asyncio
    async def test_create_targeting_rule(self, mock_pool, valid_targeting_rule, mock_connection):
        """Test creating a targeting rule."""
        service = TargetingService(mock_pool)
        result = await service.create_targeting_rule(valid_targeting_rule)
        
        assert result.id == "rule1"
        mock_connection.create_targeting_rule.assert_called_once_with({
            "name": valid_targeting_rule.name,
            "description": valid_targeting_rule.description,
            "criteria": [
                {
                    "type": c.type.value,
                    "operator": c.operator.value,
                    "values": c.values
                }
                for c in valid_targeting_rule.criteria
            ]
        })

    @pytest.mark.asyncio
    async def test_get_targeting_rule(self, mock_pool, mock_connection):
        """Test getting a targeting rule."""
        mock_connection.get_targeting_rule.return_value = {
            "id": "rule1",
            "name": "US Desktop Users",
            "description": "Target users in US on desktop devices",
            "criteria": [
                {
                    "type": "GEOGRAPHY",
                    "operator": "IS",
                    "values": ["US"]
                },
                {
                    "type": "DEVICE",
                    "operator": "IS",
                    "values": ["DESKTOP"]
                }
            ],
            "createdAt": datetime.now(timezone.UTC).isoformat(),
            "updatedAt": datetime.now(timezone.UTC).isoformat()
        }
        
        service = TargetingService(mock_pool)
        result = await service.get_targeting_rule("rule1")
        
        assert result.id == "rule1"
        assert result.name == "US Desktop Users"
        assert len(result.criteria) == 2
        mock_connection.get_targeting_rule.assert_called_once_with("rule1") 