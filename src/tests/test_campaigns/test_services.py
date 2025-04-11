"""Tests for campaign management service."""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone, timedelta

from src.campaigns.models import Order, LineItem, Creative
from src.campaigns.services import CampaignService
from src.campaigns.line_items.connection_pool import ConnectionPool

@pytest.fixture
def mock_connection():
    """Create a mock connection."""
    connection = AsyncMock()
    
    # Mock successful responses
    connection.execute_batch.return_value = {
        "status": "success",
        "operations": [
            {"id": "op1", "status": "success"},
            {"id": "op2", "status": "success"},
            {"id": "op3", "status": "success"}
        ]
    }
    
    connection.get_order.return_value = {
        "id": "order1",
        "name": "Test Order",
        "status": "ACTIVE",
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
def valid_order():
    """Create a valid order for testing."""
    return Order(
        name="Test Order",
        advertiser_id="123",
        start_datetime=datetime.now(timezone.UTC),
        end_datetime=datetime.now(timezone.UTC) + timedelta(days=30)
    )

@pytest.fixture
def valid_line_item(valid_order):
    """Create a valid line item for testing."""
    return LineItem(
        name="Test Line Item",
        order_id=valid_order.id or "order1",
        start_datetime=valid_order.start_datetime,
        end_datetime=valid_order.end_datetime,
        targeting={"geo": "US"}
    )

@pytest.fixture
def valid_creative():
    """Create a valid creative for testing."""
    return Creative(
        name="Test Creative",
        size={"width": 300, "height": 250},
        preview_url="http://example.com/preview.jpg"
    )

class TestCampaignService:
    """Test cases for CampaignService."""

    @pytest.mark.asyncio
    async def test_create_campaign(self, mock_pool, valid_order, valid_line_item, valid_creative, mock_connection):
        """Test creating a complete campaign."""
        service = CampaignService(mock_pool)
        result = await service.create_campaign(
            order=valid_order,
            line_items=[valid_line_item],
            creatives=[valid_creative]
        )
        
        assert result["status"] == "success"
        assert len(result["data"]["operations"]) == 3
        mock_connection.execute_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_campaign(self, mock_pool, mock_connection):
        """Test updating campaign components."""
        service = CampaignService(mock_pool)
        
        order_updates = {
            "id": "order1",
            "name": "Updated Order",
            "status": "PAUSED"
        }
        
        line_item_updates = {
            "lineitem1": {
                "name": "Updated Line Item",
                "status": "PAUSED"
            }
        }
        
        result = await service.update_campaign(
            order_updates=order_updates,
            line_item_updates=line_item_updates
        )
        
        assert result["status"] == "success"
        mock_connection.execute_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_campaign(self, mock_pool, mock_connection):
        """Test getting campaign details."""
        # Mock line items response
        mock_connection.get_line_items_by_order = AsyncMock(return_value={
            "status": "success",
            "data": {
                "results": [
                    {
                        "id": "lineitem1",
                        "name": "Test Line Item",
                        "creative_ids": ["creative1"]
                    }
                ]
            }
        })
        
        # Mock creatives response
        mock_connection.get_creatives = AsyncMock(return_value={
            "status": "success",
            "creatives": [
                {
                    "id": "creative1",
                    "name": "Test Creative"
                }
            ]
        })
        
        service = CampaignService(mock_pool)
        result = await service.get_campaign("order1")
        
        assert result["status"] == "success"
        assert "order" in result["data"]
        assert "line_items" in result["data"]
        assert "creatives" in result["data"]
        mock_connection.get_order.assert_called_once_with("order1")

    @pytest.mark.asyncio
    async def test_pause_campaign(self, mock_pool, mock_connection):
        """Test pausing a campaign."""
        # Mock get_campaign response
        mock_connection.get_line_items_by_order = AsyncMock(return_value={
            "status": "success",
            "data": {
                "results": [
                    {
                        "id": "lineitem1",
                        "status": "ACTIVE"
                    }
                ]
            }
        })
        
        service = CampaignService(mock_pool)
        result = await service.pause_campaign("order1")
        
        assert result["status"] == "success"
        mock_connection.execute_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_campaign(self, mock_pool, mock_connection):
        """Test resuming a campaign."""
        # Mock get_campaign response
        mock_connection.get_line_items_by_order = AsyncMock(return_value={
            "status": "success",
            "data": {
                "results": [
                    {
                        "id": "lineitem1",
                        "status": "PAUSED"
                    }
                ]
            }
        })
        
        service = CampaignService(mock_pool)
        result = await service.resume_campaign("order1")
        
        assert result["status"] == "success"
        mock_connection.execute_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_campaign(self, mock_pool, mock_connection):
        """Test archiving a campaign."""
        # Mock get_campaign response
        mock_connection.get_line_items_by_order = AsyncMock(return_value={
            "status": "success",
            "data": {
                "results": [
                    {
                        "id": "lineitem1",
                        "status": "ACTIVE"
                    }
                ]
            }
        })
        
        service = CampaignService(mock_pool)
        result = await service.archive_campaign("order1")
        
        assert result["status"] == "success"
        mock_connection.execute_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_pool, mock_connection):
        """Test error handling in campaign operations."""
        # Mock error response
        mock_connection.execute_batch.side_effect = Exception("Network error")
        
        service = CampaignService(mock_pool)
        result = await service.create_campaign(
            order=Order(
                name="Test Order",
                advertiser_id="123",
                start_datetime=datetime.now(timezone.UTC),
                end_datetime=datetime.now(timezone.UTC) + timedelta(days=30)
            ),
            line_items=[
                LineItem(
                    name="Test Line Item",
                    order_id="order1",
                    start_datetime=datetime.now(timezone.UTC),
                    end_datetime=datetime.now(timezone.UTC) + timedelta(days=30),
                    targeting={"geo": "US"}
                )
            ]
        )
        
        assert result["status"] == "error"
        assert "Failed to create campaign" in result["message"] 