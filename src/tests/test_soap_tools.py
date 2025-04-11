import pytest
from copy import deepcopy
from unittest.mock import Mock, patch
from src.tools.soap_tools import SoapToolAdapter
from src.tools.tool_registry import ToolRegistry
from src.auth.errors import AuthError
from src.auth.soap_client import GoogleAdManagerClient

@pytest.fixture
def valid_config():
    return {
        "client": {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "refresh_token": "test_refresh_token",
            "network_code": "12345678",
            "application_name": "MCP_Test",
            "wsdl_url": "https://ads.google.com/apis/ads/publisher/v202308/NetworkService?wsdl"
        }
    }

@pytest.fixture
def registry():
    return ToolRegistry()

class TestSoapToolAdapter:
    async def test_initialize_client_success(self, valid_config, registry):
        """Test successful initialization of client with valid config."""
        with patch('src.tools.soap_tools.GoogleAdManagerClient') as mock_client:
            mock_client.return_value = Mock(spec=GoogleAdManagerClient)
            adapter = SoapToolAdapter(registry)
            result = await adapter.initialize_client(valid_config)
            
            assert result["status"] == "success"
            assert "SOAP client initialized successfully" in result["message"]
            assert adapter.client is not None
            assert adapter.config == adapter._config
        
    async def test_initialize_client_missing_fields(self, registry):
        """Test initialization with missing required fields."""
        adapter = SoapToolAdapter(registry)
        invalid_config = {"client": {"client_id": "test"}}
        
        result = await adapter.initialize_client(invalid_config)
        
        assert result["status"] == "error"
        assert "Missing required configuration fields" in result["message"]
        assert adapter._client is None
        
    async def test_initialize_client_auth_error(self, valid_config, registry):
        """Test initialization with auth error."""
        with patch('src.tools.soap_tools.GoogleAdManagerClient') as mock_client:
            mock_client.side_effect = AuthError(
                message="Invalid credentials",
                operation="client_initialization",
                details={"error": "Invalid client secret"}
            )
            adapter = SoapToolAdapter(registry)
            config = deepcopy(valid_config)
            config["client"]["client_secret"] = "invalid"
            
            result = await adapter.initialize_client(config)
            
            assert result["status"] == "error"
            assert isinstance(adapter._last_error, AuthError)
            assert adapter._client is None

class TestSoapTools:
    @pytest.fixture
    async def tools(self, registry):
        adapter = SoapToolAdapter(registry)
        adapter.register_tools()
        return registry
        
    async def test_initialize_soap_success(self, valid_config, tools):
        """Test successful SOAP initialization."""
        with patch('src.tools.soap_tools.GoogleAdManagerClient') as mock_client:
            mock_client.return_value = Mock(spec=GoogleAdManagerClient)
            result = await tools.get_tool("soap.initialize")(valid_config)
            assert result["status"] == "success"
            assert "SOAP client initialized successfully" in result["message"]
        
    async def test_initialize_soap_error(self, tools):
        """Test SOAP initialization with error."""
        invalid_config = {"client": {"client_id": "test"}}
        result = await tools.get_tool("soap.initialize")(invalid_config)
        assert result["status"] == "error"
        assert "Missing required configuration fields" in result["message"] 