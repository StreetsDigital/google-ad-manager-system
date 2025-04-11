"""Tests for campaign batch validators."""

import pytest
from datetime import datetime, timedelta
from src.campaigns.models import (
    Order, LineItem, Creative, TargetingRule, BatchOperation
)
from src.campaigns.batch.validators import BatchValidator, ValidationError

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

@pytest.fixture
def valid_targeting_rule():
    """Get a valid targeting rule."""
    return TargetingRule(
        name="Test Rule",
        type="GEO",
        criteria={"country": "US"}
    )

class TestBatchValidator:
    """Test cases for BatchValidator."""

    def test_validate_order_success(self, valid_order):
        """Test successful order validation."""
        validator = BatchValidator()
        validator.validate_order(valid_order)  # Should not raise

    def test_validate_order_past_start_time(self, future_datetime):
        """Test order validation with past start time."""
        order = Order(
            name="Past Order",
            advertiser_id="123",
            start_datetime=datetime.utcnow() - timedelta(days=1),
            end_datetime=future_datetime
        )
        
        with pytest.raises(ValidationError) as exc_info:
            BatchValidator.validate_order(order)
        assert "Order start time cannot be in the past" in str(exc_info.value)

    def test_validate_order_invalid_duration(self, future_datetime):
        """Test order validation with duration > 1 year."""
        order = Order(
            name="Long Order",
            advertiser_id="123",
            start_datetime=future_datetime,
            end_datetime=future_datetime + timedelta(days=400)
        )
        
        with pytest.raises(ValidationError) as exc_info:
            BatchValidator.validate_order(order)
        assert "Order duration cannot exceed 1 year" in str(exc_info.value)

    def test_validate_line_item_success(self, valid_line_item, valid_order):
        """Test successful line item validation."""
        validator = BatchValidator()
        validator.validate_line_item(valid_line_item, valid_order)  # Should not raise

    def test_validate_line_item_outside_order_dates(self, valid_order):
        """Test line item validation with dates outside order range."""
        line_item = LineItem(
            name="Invalid Line Item",
            order_id="456",
            start_datetime=valid_order.start_datetime - timedelta(days=1),
            end_datetime=valid_order.end_datetime,
            targeting={"geo": "US"}
        )
        
        with pytest.raises(ValidationError) as exc_info:
            BatchValidator.validate_line_item(line_item, valid_order)
        assert "Line item start time cannot be before order start time" in str(exc_info.value)

    def test_validate_creative_success(self, valid_creative):
        """Test successful creative validation."""
        validator = BatchValidator()
        validator.validate_creative(valid_creative)  # Should not raise

    def test_validate_creative_invalid_size(self):
        """Test creative validation with invalid size."""
        creative = Creative(
            name="Invalid Creative",
            advertiser_id="123",
            size={"width": 0, "height": 250},
            preview_url="http://example.com/preview.jpg"
        )
        
        with pytest.raises(ValidationError) as exc_info:
            BatchValidator.validate_creative(creative)
        assert "Creative dimensions must be positive" in str(exc_info.value)

    def test_validate_targeting_rule_success(self, valid_targeting_rule):
        """Test successful targeting rule validation."""
        validator = BatchValidator()
        validator.validate_targeting_rule(valid_targeting_rule)  # Should not raise

    def test_validate_targeting_rule_invalid_type(self):
        """Test targeting rule validation with invalid type."""
        rule = TargetingRule(
            name="Invalid Rule",
            type="INVALID",
            criteria={"country": "US"}
        )
        
        with pytest.raises(ValidationError) as exc_info:
            BatchValidator.validate_targeting_rule(rule)
        assert "Invalid targeting rule type" in str(exc_info.value)

    def test_validate_batch_operation_success(self, valid_order):
        """Test successful batch operation validation."""
        operation = BatchOperation(
            operation_id="test_op",
            operation_type="CREATE",
            entity_type="ORDER",
            data=valid_order.dict()
        )
        
        validator = BatchValidator()
        validator.validate_batch_operation(operation)  # Should not raise

    def test_validate_batch_operation_invalid_type(self, valid_order):
        """Test batch operation validation with invalid operation type."""
        operation = BatchOperation(
            operation_id="test_op",
            operation_type="INVALID",
            entity_type="ORDER",
            data=valid_order.dict()
        )
        
        with pytest.raises(ValidationError) as exc_info:
            BatchValidator.validate_batch_operation(operation)
        assert "Invalid operation type" in str(exc_info.value)

    def test_validate_batch_success(self, valid_order, valid_line_item):
        """Test successful batch validation."""
        operations = [
            BatchOperation(
                operation_id="op1",
                operation_type="CREATE",
                entity_type="ORDER",
                data=valid_order.dict()
            ),
            BatchOperation(
                operation_id="op2",
                operation_type="CREATE",
                entity_type="LINE_ITEM",
                data=valid_line_item.dict()
            )
        ]
        
        validator = BatchValidator()
        validator.validate_batch(operations)  # Should not raise

    def test_validate_batch_empty(self):
        """Test batch validation with empty batch."""
        validator = BatchValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_batch([])
        assert "Batch cannot be empty" in str(exc_info.value)

    def test_validate_batch_cross_validation(self, valid_order):
        """Test batch validation with cross-entity validation."""
        # Create a line item that ends after its order
        invalid_line_item = LineItem(
            name="Invalid Line Item",
            order_id=valid_order.operation_id,
            start_datetime=valid_order.start_datetime,
            end_datetime=valid_order.end_datetime + timedelta(days=1),
            targeting={"geo": "US"}
        )
        
        operations = [
            BatchOperation(
                operation_id="op1",
                operation_type="CREATE",
                entity_type="ORDER",
                data=valid_order.dict()
            ),
            BatchOperation(
                operation_id="op2",
                operation_type="CREATE",
                entity_type="LINE_ITEM",
                data=invalid_line_item.dict()
            )
        ]
        
        validator = BatchValidator()
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_batch(operations)
        assert "Line item end time cannot be after order end time" in str(exc_info.value) 