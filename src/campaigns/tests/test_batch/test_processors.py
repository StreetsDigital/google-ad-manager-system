"""Tests for campaign batch processors."""

import pytest
from datetime import datetime, timedelta
from src.campaigns.models import Order, LineItem, Creative, BatchOperation
from src.campaigns.batch.processors import (
    OrderProcessor, LineItemProcessor, CreativeProcessor, CampaignProcessor
)
from src.campaigns.batch.validators import ValidationError

@pytest.fixture
def future_datetime():
    """Get a datetime in the future."""
    return datetime.utcnow() + timedelta(days=1)

@pytest.fixture
def valid_order(future_datetime):
    """Get a valid order."""
    return Order(
        name="Test Order",
        advertiser_id="123",
        start_datetime=future_datetime,
        end_datetime=future_datetime + timedelta(days=30)
    )

@pytest.fixture
def valid_line_item(valid_order):
    """Get a valid line item."""
    return LineItem(
        name="Test Line Item",
        order_id="456",
        start_datetime=valid_order.start_datetime,
        end_datetime=valid_order.end_datetime,
        targeting={"geo": "US"}
    )

@pytest.fixture
def valid_creative():
    """Get a valid creative."""
    return Creative(
        name="Test Creative",
        advertiser_id="123",
        size={"width": 300, "height": 250},
        preview_url="http://example.com/preview.jpg"
    )

class TestOrderProcessor:
    """Test cases for OrderProcessor."""

    def test_prepare_create(self, valid_order):
        """Test preparing a create order operation."""
        processor = OrderProcessor()
        operation = processor.prepare_create(valid_order)
        
        assert isinstance(operation, BatchOperation)
        assert operation.operation_type == "CREATE"
        assert operation.entity_type == "ORDER"
        assert operation.data == valid_order.dict()
        assert operation.operation_id.startswith("create_order_")
    
    def test_prepare_update(self):
        """Test preparing an update order operation."""
        processor = OrderProcessor()
        updates = {"name": "Updated Order", "status": "PAUSED"}
        operation = processor.prepare_update("order_123", updates)
        
        assert isinstance(operation, BatchOperation)
        assert operation.operation_type == "UPDATE"
        assert operation.entity_type == "ORDER"
        assert operation.data["id"] == "order_123"
        assert operation.data["name"] == "Updated Order"
        assert operation.data["status"] == "PAUSED"

class TestLineItemProcessor:
    """Test cases for LineItemProcessor."""

    def test_prepare_create(self, valid_line_item):
        """Test preparing a create line item operation."""
        processor = LineItemProcessor()
        operation = processor.prepare_create(valid_line_item)
        
        assert isinstance(operation, BatchOperation)
        assert operation.operation_type == "CREATE"
        assert operation.entity_type == "LINE_ITEM"
        assert operation.data == valid_line_item.dict()
        assert operation.operation_id.startswith("create_lineitem_")
    
    def test_prepare_update(self):
        """Test preparing an update line item operation."""
        processor = LineItemProcessor()
        updates = {"name": "Updated Line Item", "status": "PAUSED"}
        operation = processor.prepare_update("lineitem_123", updates)
        
        assert isinstance(operation, BatchOperation)
        assert operation.operation_type == "UPDATE"
        assert operation.entity_type == "LINE_ITEM"
        assert operation.data["id"] == "lineitem_123"
        assert operation.data["name"] == "Updated Line Item"
        assert operation.data["status"] == "PAUSED"

class TestCreativeProcessor:
    """Test cases for CreativeProcessor."""

    def test_prepare_create(self, valid_creative):
        """Test preparing a create creative operation."""
        processor = CreativeProcessor()
        operation = processor.prepare_create(valid_creative)
        
        assert isinstance(operation, BatchOperation)
        assert operation.operation_type == "CREATE"
        assert operation.entity_type == "CREATIVE"
        assert operation.data == valid_creative.dict()
        assert operation.operation_id.startswith("create_creative_")
    
    def test_prepare_update(self):
        """Test preparing an update creative operation."""
        processor = CreativeProcessor()
        updates = {"name": "Updated Creative", "preview_url": "http://new.example.com/preview.jpg"}
        operation = processor.prepare_update("creative_123", updates)
        
        assert isinstance(operation, BatchOperation)
        assert operation.operation_type == "UPDATE"
        assert operation.entity_type == "CREATIVE"
        assert operation.data["id"] == "creative_123"
        assert operation.data["name"] == "Updated Creative"
        assert operation.data["preview_url"] == "http://new.example.com/preview.jpg"

class TestCampaignProcessor:
    """Test cases for CampaignProcessor."""

    def test_prepare_campaign_create(self, valid_order, valid_line_item, valid_creative):
        """Test preparing a complete campaign creation."""
        processor = CampaignProcessor()
        operations = processor.prepare_campaign_create(
            order=valid_order,
            line_items=[valid_line_item],
            creatives=[valid_creative]
        )
        
        assert len(operations) == 3
        assert operations[0].entity_type == "ORDER"
        assert operations[1].entity_type == "LINE_ITEM"
        assert operations[2].entity_type == "CREATIVE"
        
        # Verify order operation
        assert operations[0].operation_type == "CREATE"
        assert operations[0].data == valid_order.dict()
        
        # Verify line item operation
        assert operations[1].operation_type == "CREATE"
        assert operations[1].data == valid_line_item.dict()
        
        # Verify creative operation
        assert operations[2].operation_type == "CREATE"
        assert operations[2].data == valid_creative.dict()
    
    def test_prepare_campaign_update(self):
        """Test preparing campaign updates."""
        processor = CampaignProcessor()
        
        order_updates = {
            "id": "order_123",
            "name": "Updated Order",
            "status": "PAUSED"
        }
        
        line_item_updates = {
            "lineitem_123": {
                "name": "Updated Line Item",
                "status": "PAUSED"
            }
        }
        
        creative_updates = {
            "creative_123": {
                "name": "Updated Creative",
                "preview_url": "http://new.example.com/preview.jpg"
            }
        }
        
        operations = processor.prepare_campaign_update(
            order_updates=order_updates,
            line_item_updates=line_item_updates,
            creative_updates=creative_updates
        )
        
        assert len(operations) == 3
        
        # Verify order update
        assert operations[0].operation_type == "UPDATE"
        assert operations[0].entity_type == "ORDER"
        assert operations[0].data["id"] == "order_123"
        assert operations[0].data["name"] == "Updated Order"
        
        # Verify line item update
        assert operations[1].operation_type == "UPDATE"
        assert operations[1].entity_type == "LINE_ITEM"
        assert operations[1].data["id"] == "lineitem_123"
        assert operations[1].data["name"] == "Updated Line Item"
        
        # Verify creative update
        assert operations[2].operation_type == "UPDATE"
        assert operations[2].entity_type == "CREATIVE"
        assert operations[2].data["id"] == "creative_123"
        assert operations[2].data["name"] == "Updated Creative"
    
    def test_validation_error_handling(self, valid_order):
        """Test validation error handling in campaign processor."""
        processor = CampaignProcessor()
        
        # Create an invalid line item (end time before start time)
        invalid_line_item = LineItem(
            name="Invalid Line Item",
            order_id="456",
            start_datetime=valid_order.start_datetime + timedelta(days=1),
            end_datetime=valid_order.start_datetime,
            targeting={"geo": "US"}
        )
        
        with pytest.raises(ValidationError) as exc_info:
            processor.prepare_campaign_create(
                order=valid_order,
                line_items=[invalid_line_item]
            )
        
        assert "Line item end time must be after start time" in str(exc_info.value) 