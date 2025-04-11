"""Tests for the FastMCP server implementation."""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
from typing import Dict, List

from src.tools.tool_registry import ToolRegistry, auto_tool
from src.mcp.server.fastmcp import FastMCPServer, ToolRequest, ToolResponse

@pytest.fixture
def registry():
    """Create a fresh ToolRegistry for each test."""
    return ToolRegistry()

@pytest.fixture
def server(registry):
    """Create a FastMCP server instance."""
    return FastMCPServer(registry)

@pytest.fixture
def client(server):
    """Create a test client."""
    return TestClient(server.app)

@pytest.fixture
def sample_tools(registry):
    """Register sample tools for testing."""
    
    @auto_tool(registry, name="add", description="Add two numbers")
    async def add(x: int, y: int) -> int:
        return x + y
    
    @auto_tool(registry, name="concat", description="Concatenate strings")
    async def concat(strings: List[str]) -> str:
        return " ".join(strings)
    
    @auto_tool(registry, name="echo", description="Echo back the input")
    async def echo(data: Dict[str, str]) -> Dict[str, str]:
        return data

def test_list_tools_empty(client, registry):
    """Test listing tools when registry is empty."""
    response = client.get("/tools")
    assert response.status_code == 200
    assert response.json() == []

def test_list_tools(client, sample_tools):
    """Test listing registered tools."""
    response = client.get("/tools")
    assert response.status_code == 200
    tools = response.json()
    
    assert len(tools) == 3
    tool_names = {t["name"] for t in tools}
    assert tool_names == {"add", "concat", "echo"}

def test_get_tool_info(client, sample_tools):
    """Test getting information about a specific tool."""
    response = client.get("/tools/add")
    assert response.status_code == 200
    
    tool_info = response.json()
    assert tool_info["name"] == "add"
    assert tool_info["description"] == "Add two numbers"
    assert "x" in tool_info["parameters"]
    assert "y" in tool_info["parameters"]
    assert tool_info["parameters"]["x"] == "<class 'int'>"
    assert tool_info["parameters"]["y"] == "<class 'int'>"

def test_get_nonexistent_tool_info(client):
    """Test getting info for a non-existent tool."""
    response = client.get("/tools/nonexistent")
    assert response.status_code == 404

def test_execute_tool(client, sample_tools):
    """Test executing a tool successfully."""
    response = client.post(
        "/tools/add",
        json={"parameters": {"x": 5, "y": 3}}
    )
    assert response.status_code == 200
    
    result = response.json()
    assert result["result"] == 8
    assert result["error"] is None
    assert isinstance(result["execution_time"], float)
    assert isinstance(result["timestamp"], str)

def test_execute_tool_with_invalid_parameters(client, sample_tools):
    """Test executing a tool with invalid parameters."""
    response = client.post(
        "/tools/add",
        json={"parameters": {"x": "not_a_number", "y": 3}}
    )
    assert response.status_code == 200  # Still returns 200 but with error
    assert response.json()["error"] is not None

def test_execute_nonexistent_tool(client):
    """Test executing a non-existent tool."""
    response = client.post(
        "/tools/nonexistent",
        json={"parameters": {}}
    )
    assert response.status_code == 404

def test_execute_tool_with_complex_input(client, sample_tools):
    """Test executing a tool with complex input types."""
    response = client.post(
        "/tools/echo",
        json={"parameters": {"data": {"key1": "value1", "key2": "value2"}}}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["result"] == {"key1": "value1", "key2": "value2"}

def test_execute_tool_with_list_input(client, sample_tools):
    """Test executing a tool with list input."""
    response = client.post(
        "/tools/concat",
        json={"parameters": {"strings": ["Hello", "World"]}}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["result"] == "Hello World"

def test_cors_headers(client):
    """Test that CORS headers are properly set."""
    response = client.get("/tools")
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "*"

def test_options_request(client):
    """Test handling of OPTIONS requests."""
    response = client.options("/tools")
    assert response.status_code == 200
    assert "access-control-allow-methods" in response.headers
    assert "GET, POST, OPTIONS" in response.headers["access-control-allow-methods"]

def test_tool_execution_timing(client, sample_tools):
    """Test that tool execution timing is recorded."""
    response = client.post(
        "/tools/add",
        json={"parameters": {"x": 1, "y": 2}}
    )
    assert response.status_code == 200
    result = response.json()
    
    assert "execution_time" in result
    assert isinstance(result["execution_time"], float)
    assert result["execution_time"] >= 0

def test_tool_execution_timestamp(client, sample_tools):
    """Test that tool execution timestamp is recorded."""
    response = client.post(
        "/tools/add",
        json={"parameters": {"x": 1, "y": 2}}
    )
    assert response.status_code == 200
    result = response.json()
    
    assert "timestamp" in result
    # Verify timestamp can be parsed
    timestamp = datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00"))
    assert isinstance(timestamp, datetime) 