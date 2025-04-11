"""Tests for campaign batch operations."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from src.campaigns.models import Order, LineItem, Creative, BatchOperation
from src.campaigns.batch.operations import CampaignBatchProcessor
from src.tools.soap_tools import SoapToolAdapter

@pytest.fixture
def mock_adapter():
    """Get a mock SOAP tool adapter."""
    adapter = Mock(spec=SoapToolAdapter)
    adapter.registry = Mock()
    adapter.registry.get_tool = AsyncMock()
    return adapter

@pytest.fixture
def mock_batch_tool():
    """Get a mock batch tool."""
    return AsyncMock()

@pytest.fixture
def mock_status_tool():
    """Get a mock status tool."""
    return AsyncMock()

@pytest.fixture
def processor(mock_adapter, mock_batch_tool, mock_status_tool):
    """Get a campaign batch processor."""
    # Configure the get_tool mock to return appropriate tools
    async def get_tool(tool_name):
        if tool_name == "batch":
            return mock_batch_tool
        elif tool_name == "status":
            return mock_status_tool
        raise ValueError(f"Unknown tool: {tool_name}")
    
    mock_adapter.registry.get_tool.side_effect = get_tool
    return CampaignBatchProcessor(mock_adapter)

@pytest.fixture
def sample_operations():
    """Get sample batch operations."""
    return [
        BatchOperation(
            operation_id="op1",
            operation_type="CREATE",
            entity_type="ORDER",
            data={"name": "Test Order"},
            created_at=datetime.now(timezone.utc)
        ),
        BatchOperation(
            operation_id="op2",
            operation_type="CREATE",
            entity_type="LINE_ITEM",
            data={"name": "Test Line Item"},
            created_at=datetime.now(timezone.utc)
        )
    ]

class TestCampaignBatchProcessor:
    """Test cases for CampaignBatchProcessor."""

    async def test_prepare_operation(self, processor):
        """Test operation preparation."""
        operation = BatchOperation(
            operation_id="test_op",
            operation_type="CREATE",
            entity_type="ORDER",
            data={"name": "Test Order"},
            created_at=datetime.now(timezone.utc)
        )
        
        result = await processor._prepare_operation(operation)
        
        assert result["id"] == "test_op"
        assert result["method"] == "createOrders"
        assert result["params"]["orders"] == [{"name": "Test Order"}]

    async def test_submit_batch_success(self, processor, mock_batch_tool, sample_operations):
        """Test successful batch submission."""
        mock_batch_tool.return_value = {
            "status": "accepted",
            "batch_id": "test_batch"
        }
        
        result = await processor.submit_batch(sample_operations)
        
        assert result["status"] == "accepted"
        assert "batch_id" in result
        assert result["operation_count"] == len(sample_operations)
        
        # Verify batch tool was called correctly
        mock_batch_tool.assert_called_once()
        call_args = mock_batch_tool.call_args[1]
        assert len(call_args["operations"]) == len(sample_operations)

    async def test_submit_batch_failure(self, processor, mock_batch_tool, sample_operations):
        """Test batch submission failure."""
        mock_batch_tool.return_value = {
            "status": "error",
            "message": "Test error"
        }
        
        result = await processor.submit_batch(sample_operations)
        
        assert result["status"] == "error"
        assert "message" in result
        assert result["message"] == "Test error"

    async def test_get_batch_status_success(self, processor, mock_status_tool, sample_operations):
        """Test successful batch status retrieval."""
        # Set up mock status response
        mock_status_tool.return_value = {
            "status": "completed",
            "total_operations": 2,
            "completed_operations": 2,
            "failed_operations": 0,
            "operations": [
                {
                    "id": "op1",
                    "status": "completed",
                    "result": {"id": "order1"}
                },
                {
                    "id": "op2",
                    "status": "completed",
                    "result": {"id": "lineitem1"}
                }
            ]
        }
        
        # Submit batch to set up active_batches
        batch_id = "test_batch"
        processor._active_batches[batch_id] = sample_operations
        
        result = await processor.get_batch_status(batch_id)
        
        assert result["status"] == "completed"
        assert result["total_operations"] == 2
        assert result["completed_operations"] == 2
        assert result["failed_operations"] == 0
        
        # Verify operations were updated
        operations = result["operations"]
        assert len(operations) == 2
        assert operations[0]["status"] == "completed"
        assert operations[1]["status"] == "completed"

    async def test_get_batch_status_not_found(self, processor, mock_status_tool):
        """Test batch status retrieval for non-existent batch."""
        result = await processor.get_batch_status("invalid_batch")
        
        assert result["status"] == "error"
        assert "not found" in result["message"]
        mock_status_tool.assert_not_called()

    async def test_get_batch_status_partial_failure(self, processor, mock_status_tool, sample_operations):
        """Test batch status retrieval with partial failure."""
        # Set up mock status response with one failed operation
        mock_status_tool.return_value = {
            "status": "completed",
            "total_operations": 2,
            "completed_operations": 1,
            "failed_operations": 1,
            "operations": [
                {
                    "id": "op1",
                    "status": "completed",
                    "result": {"id": "order1"}
                },
                {
                    "id": "op2",
                    "status": "failed",
                    "error": "Test error"
                }
            ]
        }
        
        # Submit batch to set up active_batches
        batch_id = "test_batch"
        processor._active_batches[batch_id] = sample_operations
        
        result = await processor.get_batch_status(batch_id)
        
        assert result["status"] == "completed"
        assert result["total_operations"] == 2
        assert result["completed_operations"] == 1
        assert result["failed_operations"] == 1
        
        # Verify operations were updated
        operations = result["operations"]
        assert operations[0]["status"] == "completed"
        assert operations[1]["status"] == "failed"
        assert operations[1]["error"] == "Test error"

    async def test_wait_for_batch_success(self, processor, mock_status_tool, sample_operations):
        """Test successful batch wait."""
        # Set up mock status responses to simulate completion after one check
        mock_status_tool.side_effect = [
            {
                "status": "running",
                "total_operations": 2,
                "completed_operations": 1,
                "failed_operations": 0,
                "operations": []
            },
            {
                "status": "completed",
                "total_operations": 2,
                "completed_operations": 2,
                "failed_operations": 0,
                "operations": []
            }
        ]
        
        # Submit batch to set up active_batches
        batch_id = "test_batch"
        processor._active_batches[batch_id] = sample_operations
        
        result = await processor.wait_for_batch(batch_id, timeout=10)
        
        assert result["status"] == "completed"
        assert mock_status_tool.call_count == 2

    async def test_wait_for_batch_timeout(self, processor, mock_status_tool, sample_operations):
        """Test batch wait timeout."""
        # Set up mock status to always return running
        mock_status_tool.return_value = {
            "status": "running",
            "total_operations": 2,
            "completed_operations": 1,
            "failed_operations": 0,
            "operations": []
        }
        
        # Submit batch to set up active_batches
        batch_id = "test_batch"
        processor._active_batches[batch_id] = sample_operations
        
        result = await processor.wait_for_batch(batch_id, timeout=1)
        
        assert result["status"] == "timeout"
        assert "timed out" in result["message"] 