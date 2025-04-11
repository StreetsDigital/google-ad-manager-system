"""Tests for STDIO server implementation."""

import json
import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.mcp.server.stdio import StdioServer, StdioRequest, create_stdio_server

@pytest.fixture
def mock_app():
    """Create a mock FastAPI application."""
    app = FastAPI()
    
    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}
    
    @app.post("/echo")
    async def echo_endpoint(data: dict):
        return data
    
    @app.get("/error")
    async def error_endpoint():
        raise ValueError("Test error")
    
    return app

@pytest.fixture
def stdio_server(mock_app):
    """Create a StdioServer instance with mock app."""
    return create_stdio_server(mock_app)

@pytest.mark.asyncio
async def test_handle_get_request(stdio_server):
    """Test handling GET request."""
    request = StdioRequest(
        method="GET",
        path="/test"
    )
    
    response = await stdio_server.handle_request(request)
    
    assert response["status"] == 200
    assert response["body"]["message"] == "test"

@pytest.mark.asyncio
async def test_handle_post_request(stdio_server):
    """Test handling POST request with body."""
    test_data = {"key": "value"}
    request = StdioRequest(
        method="POST",
        path="/echo",
        body=test_data
    )
    
    response = await stdio_server.handle_request(request)
    
    assert response["status"] == 200
    assert response["body"] == test_data

@pytest.mark.asyncio
async def test_handle_error_request(stdio_server):
    """Test handling request that raises error."""
    request = StdioRequest(
        method="GET",
        path="/error"
    )
    
    response = await stdio_server.handle_request(request)
    
    assert response["status"] == 500
    assert "error" in response["body"]

@pytest.mark.asyncio
async def test_process_line_valid_json(stdio_server):
    """Test processing valid JSON input."""
    with patch("builtins.print") as mock_print:
        await stdio_server.process_line(
            '{"method": "GET", "path": "/test"}'
        )
        
        mock_print.assert_called_once()
        printed_data = json.loads(mock_print.call_args[0][0])
        assert printed_data["status"] == 200
        assert printed_data["body"]["message"] == "test"

@pytest.mark.asyncio
async def test_process_line_invalid_json(stdio_server):
    """Test processing invalid JSON input."""
    with patch("builtins.print") as mock_print:
        await stdio_server.process_line("invalid json")
        
        mock_print.assert_called_once()
        printed_data = json.loads(mock_print.call_args[0][0])
        assert printed_data["status"] == 500
        assert "error" in printed_data

@pytest.mark.asyncio
async def test_process_line_missing_required_fields(stdio_server):
    """Test processing JSON missing required fields."""
    with patch("builtins.print") as mock_print:
        await stdio_server.process_line('{"method": "GET"}')
        
        mock_print.assert_called_once()
        printed_data = json.loads(mock_print.call_args[0][0])
        assert printed_data["status"] == 500
        assert "error" in printed_data

def test_create_stdio_server():
    """Test creating StdioServer instance."""
    app = FastAPI()
    server = create_stdio_server(app)
    
    assert isinstance(server, StdioServer)
    assert server.app == app

@pytest.mark.asyncio
async def test_handle_request_headers(stdio_server):
    """Test request includes proper headers."""
    request = StdioRequest(
        method="GET",
        path="/test"
    )
    
    response = await stdio_server.handle_request(request)
    
    assert "content-type" in response["headers"]
    assert response["headers"]["content-type"] == b"application/json"

@pytest.mark.asyncio
async def test_handle_request_query_params(mock_app, stdio_server):
    """Test handling request with query parameters."""
    @mock_app.get("/query")
    async def query_endpoint(param: str):
        return {"param": param}
    
    request = StdioRequest(
        method="GET",
        path="/query?param=test"
    )
    
    response = await stdio_server.handle_request(request)
    
    assert response["status"] == 200
    assert response["body"]["param"] == "test" 