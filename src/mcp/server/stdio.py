"""
STDIO interface for the MCP server.

This module provides a command-line interface to interact with the MCP server
through standard input/output streams, compatible with Cursor's MCP protocol.
"""

import sys
import json
import asyncio
from typing import Dict, Any, Optional, List
from fastapi import FastAPI
from pydantic import BaseModel, Field

class MCPRequest(BaseModel):
    """Request model for MCP communication."""
    name: str = Field(..., description="Name of the function to call")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Function parameters")

class MCPResponse(BaseModel):
    """Response model for MCP communication."""
    result: Any = Field(..., description="Result of the function call")
    error: Optional[str] = Field(None, description="Error message if the call failed")

class StdioServer:
    """STDIO interface for FastAPI server."""
    
    def __init__(self, app: FastAPI):
        """
        Initialize STDIO server.

        Args:
            app: FastAPI application instance
        """
        self.app = app
        self.loop = asyncio.get_event_loop()

    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """
        Handle incoming MCP request.

        Args:
            request: MCP request data

        Returns:
            MCPResponse: Response data
        """
        try:
            # Create scope for ASGI request
            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",  # MCP always uses POST
                "path": f"/mcp/{request.name}",
                "raw_path": f"/mcp/{request.name}".encode(),
                "query_string": b"",
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 0),
                "server": ("127.0.0.1", 0),
            }

            # Create response holder
            response_data = None

            # Define receive function
            async def receive():
                return {
                    "type": "http.request",
                    "body": json.dumps(request.parameters).encode(),
                    "more_body": False,
                }

            # Define send function
            async def send(message):
                nonlocal response_data
                if message["type"] == "http.response.body" and message["body"]:
                    response_data = json.loads(message["body"])

            # Call ASGI application
            await self.app(scope, receive, send)

            return MCPResponse(result=response_data)
        except Exception as e:
            return MCPResponse(result=None, error=str(e))

    async def process_line(self, line: str) -> None:
        """
        Process a single line of input.

        Args:
            line: Input line (JSON-encoded MCP request)
        """
        try:
            # Parse request
            data = json.loads(line)
            request = MCPRequest(**data)

            # Handle request
            response = await self.handle_request(request)

            # Send response
            print(json.dumps(response.dict(exclude_none=True)), flush=True)
        except Exception as e:
            # Send error response
            print(json.dumps({
                "error": str(e)
            }), flush=True)

    def run(self):
        """Run the STDIO server."""
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                self.loop.run_until_complete(self.process_line(line.strip()))
        except KeyboardInterrupt:
            print("Server stopped", file=sys.stderr)

def create_stdio_server(app: FastAPI) -> StdioServer:
    """
    Create a new STDIO server instance.

    Args:
        app: FastAPI application instance

    Returns:
        StdioServer: Server instance
    """
    return StdioServer(app) 