"""Tests for the SOAP tool adapter."""
import os
import json
import pytest
import asyncio
from datetime import datetime, UTC, timedelta
from unittest.mock import Mock, patch, PropertyMock, AsyncMock, MagicMock
from src.tools.tool_registry import ToolRegistry
from src.tools.soap_tools import (
    SoapToolAdapter, SoapToolConfig, RetryConfig, PoolConfig,
    BatchConfig, BatchOperation, BatchRequest
)
from src.auth.soap_client import SoapClientConfig, GoogleAdManagerClient
from src.auth.errors import AuthError, ConfigError, APIError

# Test configuration
TEST_CONFIG = {
    "client": {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "refresh_token": "test-refresh-token",
        "network_code": "test-network",
        "application_name": "MCP_Test",
        "wsdl_url": "https://test.example.com/wsdl"
    },
    "retry": {
        "max_retries": 5,
        "backoff_factor": 0.5,
        "retry_on_status": [500, 502, 503]
    },
    "pool": {
        "pool_connections": 20,
        "pool_maxsize": 20,
        "pool_block": True
    }
}

@pytest.fixture
def registry():
    """Create a fresh instance of ToolRegistry."""
    return ToolRegistry()

@pytest.fixture
def adapter(registry):
    """Create an instance of SoapToolAdapter."""
    return SoapToolAdapter(registry)

@pytest.fixture
def valid_config():
    """Get valid configuration for testing."""
    return TEST_CONFIG

@pytest.fixture
def mock_client():
    """Create a mock SOAP client."""
    with patch('src.auth.soap_client.zeep.Client') as mock_zeep_client:
        mock_service = Mock()
        mock_zeep_client.return_value.service = mock_service
        yield mock_zeep_client

@pytest.fixture
def batch_operations():
    """Get test batch operations."""
    return [
        {
            "id": "op1",
            "method": "createOrders",
            "params": {
                "advertiserId": "123",
                "orders": [{"name": "Test Order 1"}]
            }
        },
        {
            "id": "op2",
            "method": "createLineItems",
            "params": {
                "orderId": "456",
                "lineItems": [{"name": "Test Line Item 1"}]
            }
        },
        {
            "id": "op3",
            "method": "createCreatives",
            "params": {
                "advertiserId": "123",
                "creatives": [{"name": "Test Creative 1"}]
            }
        }
    ]

class TestSoapToolAdapter:
    """Test cases for SoapToolAdapter."""

    def test_initialization(self, adapter):
        """Test adapter initialization."""
        assert adapter.registry is not None
        assert adapter._client is None
        assert adapter._config is None
        assert adapter._last_error is None

    def test_client_property_not_initialized(self, adapter):
        """Test client property when not initialized."""
        with pytest.raises(RuntimeError, match="SOAP client not initialized"):
            _ = adapter.client

    def test_config_property_not_initialized(self, adapter):
        """Test config property when not initialized."""
        with pytest.raises(RuntimeError, match="SOAP tool not configured"):
            _ = adapter.config

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    def test_initialize_client_with_retry_pool(self, mock_client_class, adapter, valid_config):
        """Test client initialization with retry and pool configuration."""
        mock_instance = Mock()
        mock_client_class.return_value = mock_instance

        result = adapter.initialize_client(valid_config)
        
        assert result["status"] == "success"
        assert "retry" in result["config"]
        assert "pool" in result["config"]
        
        # Verify retry config
        retry_config = result["config"]["retry"]
        assert retry_config["max_retries"] == 5
        assert retry_config["backoff_factor"] == 0.5
        assert retry_config["retry_on_status"] == [500, 502, 503]
        
        # Verify pool config
        pool_config = result["config"]["pool"]
        assert pool_config["pool_connections"] == 20
        assert pool_config["pool_maxsize"] == 20
        assert pool_config["pool_block"] is True

        # Verify client was created with combined config
        mock_client_class.assert_called_once()
        call_args = mock_client_class.call_args[0][0]
        assert isinstance(call_args, SoapClientConfig)
        assert call_args.max_retries == 5
        assert call_args.pool_connections == 20

    def test_initialize_client_missing_required(self, adapter):
        """Test initialization with missing required fields."""
        invalid_config = {
            "client": {
                "application_name": "MCP_Test"
            }
        }
        
        result = adapter.initialize_client(invalid_config)
        assert result["status"] == "error"
        assert "Missing required configuration fields" in result["message"]
        assert set(result["details"]["missing_fields"]) == {
            "client_id", "client_secret", "refresh_token", "network_code"
        }

    def test_register_tools(self, adapter):
        """Test tool registration with parameter schemas."""
        adapter.register_tools()
        
        # Verify initialize tool
        init_tool = adapter.registry.get_tool("soap.initialize")
        assert init_tool is not None
        
        # Verify execute tool
        exec_tool = adapter.registry.get_tool("soap.execute")
        assert exec_tool is not None

class TestSoapTools:
    """Test cases for SOAP tools."""

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_initialize_soap_success(self, mock_client_class, adapter, valid_config):
        """Test successful SOAP initialization with full configuration."""
        mock_instance = Mock()
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        tool = adapter.registry.get_tool("soap.initialize")
        result = await tool(config=valid_config)
        
        assert result["status"] == "success"
        assert result["config"]["retry"]["max_retries"] == 5
        assert result["config"]["pool"]["pool_connections"] == 20

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_execute_soap_method_invalid(self, mock_client_class, adapter, valid_config):
        """Test execution of invalid SOAP method."""
        mock_instance = AsyncMock()
        mock_service = AsyncMock()
        mock_service.configure_mock(**{
            'invalid_method.side_effect': AttributeError("'Service' object has no attribute 'invalid_method'")
        })
        mock_instance.get_client = AsyncMock(return_value=MagicMock(service=mock_service))
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        await adapter.initialize_client(valid_config)
        adapter._config = SoapToolConfig(**valid_config)

        tool = adapter.registry.get_tool("soap.execute")
        result = await tool(method="invalid_method", params={})

        assert result["status"] == "error"
        assert "method 'invalid_method' not found" in result["message"].lower()

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_execute_soap_method_success(self, mock_client_class, adapter, valid_config):
        """Test successful SOAP method execution with logging."""
        mock_instance = Mock()
        mock_service = Mock()
        mock_service.test_method = AsyncMock(return_value={"data": "test"})
        mock_instance.get_client.return_value.service = mock_service
        mock_instance.execute_with_retry = AsyncMock(return_value={"data": "test"})
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        adapter.initialize_client(valid_config)
        
        tool = adapter.registry.get_tool("soap.execute")
        result = await tool(method="test_method", params={"param": "value"})
        
        assert result["status"] == "success"
        assert result["data"] == {"data": "test"}

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_get_soap_status_with_metrics(self, mock_client_class, adapter, valid_config):
        """Test getting status with metrics."""
        mock_instance = Mock()
        mock_instance.get_active_connections.return_value = 5
        mock_instance.get_request_count.return_value = 100
        mock_instance.get_error_count.return_value = 2
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        adapter.initialize_client(valid_config)
        
        tool = adapter.registry.get_tool("soap.status")
        result = await tool()
        
        assert result["status"] == "active"
        assert "metrics" in result
        assert result["metrics"]["active_connections"] == 5
        assert result["metrics"]["request_count"] == 100
        assert result["metrics"]["error_count"] == 2
        
        # Verify sensitive data is masked
        assert result["config"]["client"]["client_secret"] == "***"
        assert result["config"]["client"]["refresh_token"] == "***"

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_error_tracking(self, mock_client_class, adapter, valid_config):
        """Test error tracking across operations."""
        mock_instance = AsyncMock()
        mock_service = AsyncMock()
        test_error = Exception("Test error")
        mock_service.configure_mock(**{
            'test_method.side_effect': test_error
        })
        mock_instance.get_client = AsyncMock(return_value=MagicMock(service=mock_service))
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        await adapter.initialize_client(valid_config)
        adapter._config = SoapToolConfig(**valid_config)

        # Execute method to trigger error
        exec_tool = adapter.registry.get_tool("soap.execute")
        result = await exec_tool(method="test_method", params={})

        assert result["status"] == "error"
        assert result["message"] == "Failed to execute SOAP method: Test error"
        
        # Check error is tracked in status
        status_tool = adapter.registry.get_tool("soap.status")
        status = await status_tool()
        assert status["last_error"] == "Test error"

class TestBatchOperations:
    """Test cases for batch operations."""

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_batch_execution_success(self, mock_client_class, adapter, valid_config, batch_operations):
        """Test successful batch execution."""
        mock_instance = Mock()
        mock_service = Mock()
        
        # Mock successful operations
        mock_service.createOrders = AsyncMock(return_value={"id": "order1"})
        mock_service.createLineItems = AsyncMock(return_value={"id": "lineitem1"})
        mock_service.createCreatives = AsyncMock(return_value={"id": "creative1"})
        
        mock_instance.get_client.return_value.service = mock_service
        mock_instance.execute_with_retry = AsyncMock(side_effect=[
            {"id": "order1"},
            {"id": "lineitem1"},
            {"id": "creative1"}
        ])
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        adapter.initialize_client(valid_config)
        
        # Start batch execution
        tool = adapter.registry.get_tool("soap.batch")
        result = await tool(operations=batch_operations)
        
        # Wait for batch to complete
        await asyncio.sleep(0.1)
        
        # Check batch status
        status_tool = adapter.registry.get_tool("soap.batch.status")
        status = await status_tool(batch_id=result["batch_id"])
        
        assert status["status"] == "completed"
        assert status["total_operations"] == 3
        assert status["completed_operations"] == 3
        assert status["failed_operations"] == 0
        
        # Verify operation results
        operations = {op["id"]: op for op in status["operations"]}
        assert operations["op1"]["status"] == "completed"
        assert operations["op1"]["result"]["id"] == "order1"
        assert operations["op2"]["status"] == "completed"
        assert operations["op2"]["result"]["id"] == "lineitem1"
        assert operations["op3"]["status"] == "completed"
        assert operations["op3"]["result"]["id"] == "creative1"

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_batch_execution_partial_failure(self, mock_client_class, adapter, valid_config, batch_operations):
        """Test batch execution with some operations failing."""
        mock_instance = Mock()
        mock_service = Mock()
        
        # Mock mixed success/failure
        mock_service.createOrders = AsyncMock(return_value={"id": "order1"})
        network_error = Exception("Network error")
        mock_service.createLineItems = AsyncMock(side_effect=network_error)
        mock_service.createCreatives = AsyncMock(return_value={"id": "creative1"})
        
        mock_instance.get_client.return_value.service = mock_service
        mock_instance.execute_with_retry = AsyncMock(side_effect=[
            {"id": "order1"},
            network_error,
            {"id": "creative1"}
        ])
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        adapter.initialize_client(valid_config)
        
        # Start batch execution
        tool = adapter.registry.get_tool("soap.batch")
        result = await tool(operations=batch_operations)
        
        # Wait for batch to complete
        await asyncio.sleep(0.1)
        
        # Check batch status
        status_tool = adapter.registry.get_tool("soap.batch.status")
        status = await status_tool(batch_id=result["batch_id"])
        
        assert status["status"] == "completed"
        assert status["total_operations"] == 3
        assert status["completed_operations"] == 2
        assert status["failed_operations"] == 1
        
        # Verify operation statuses
        operations = {op["id"]: op for op in status["operations"]}
        assert operations["op1"]["status"] == "completed"
        assert operations["op2"]["status"] == "failed"
        assert operations["op2"]["error"] == "Network error"
        assert operations["op3"]["status"] == "completed"

    async def test_batch_size_limit(self, adapter, valid_config):
        """Test batch size limit enforcement."""
        config = {
            **valid_config,
            "batch": {"max_batch_size": 5}
        }
        adapter.register_tools()
        await adapter.initialize_client(config)
        adapter._config = SoapToolConfig(**config)

        # Create operations exceeding limit
        max_size = adapter.config.batch.max_batch_size
        operations = [
            {
                "id": f"op{i}",
                "method": "createOrders",
                "params": {"advertiserId": "123"}
            }
            for i in range(max_size + 1)
        ]

        tool = adapter.registry.get_tool("soap.batch")
        result = await tool(operations=operations)

        assert result["status"] == "error"
        assert "batch size exceeds maximum" in result["message"].lower()

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_batch_concurrency_control(self, mock_client_class, adapter, valid_config, batch_operations):
        """Test batch concurrency control."""
        mock_instance = AsyncMock()
        mock_service = AsyncMock()
        mock_service.createOrders = AsyncMock(return_value={"id": "test"})
        mock_instance.get_client.return_value.service = mock_service
        mock_client_class.return_value = mock_instance

        adapter.register_tools()
        adapter.initialize_client(valid_config)
        adapter._config = SoapToolConfig(**valid_config)

        # Create multiple batches
        tool = adapter.registry.get_tool("soap.batch")
        batch_results = []

        for i in range(5):  # Create 5 batches
            result = await tool(operations=batch_operations)
            assert result["status"] == "accepted"
            batch_results.append(result)

    async def test_invalid_batch_id(self, adapter, valid_config):
        """Test getting status of non-existent batch."""
        adapter.register_tools()
        adapter.initialize_client(valid_config)
        
        status_tool = adapter.registry.get_tool("soap.batch.status")
        result = await status_tool(batch_id="invalid_batch")
        
        assert result["status"] == "error"
        assert "Batch invalid_batch not found" in result["message"]

    @patch('src.tools.soap_tools.GoogleAdManagerClient')
    async def test_batch_timeout(self, mock_client_class, adapter, valid_config):
        """Test batch operation timeout."""
        mock_instance = AsyncMock()
        mock_service = AsyncMock()

        # Mock a slow operation that will timeout
        async def slow_operation(*args, **kwargs):
            await asyncio.sleep(2)  # Longer than timeout
            return {"id": "test"}

        mock_service.configure_mock(**{
            'createOrders.side_effect': slow_operation
        })
        mock_instance.get_client = AsyncMock(return_value=MagicMock(service=mock_service))
        mock_client_class.return_value = mock_instance

        # Set a short timeout for testing
        config = {
            **valid_config,
            "batch": {"timeout_seconds": 0.5}  # 0.5 second timeout
        }
        adapter.register_tools()
        await adapter.initialize_client(config)
        adapter._config = SoapToolConfig(**config)

        # Start batch execution
        tool = adapter.registry.get_tool("soap.batch")
        result = await tool(operations=[{
            "id": "op1",
            "method": "createOrders",
            "params": {"advertiserId": "123"}
        }])

        assert result["status"] == "accepted"
        
        # Wait for the operation to timeout
        await asyncio.sleep(1)  # Wait longer than the timeout

        # Check status
        status_tool = adapter.registry.get_tool("soap.batch.status")
        status = await status_tool(batch_id=result["batch_id"])
        assert status["status"] == "timeout" 