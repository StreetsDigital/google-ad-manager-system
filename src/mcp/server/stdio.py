"""
STDIO interface for the MCP server.

This module provides a command-line interface to interact with the MCP server
through standard input/output streams.
"""

import sys
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel

class StdioRequest(BaseModel):
    """Request model for stdio communication."""
    method: str
    path: str
    body: Optional[Dict[str, Any]] = None

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

    async def handle_request(self, request: StdioRequest) -> Dict[str, Any]:
        """
        Handle incoming request.

        Args:
            request: Request data

        Returns:
            Dict[str, Any]: Response data
        """
        # Create scope for ASGI request
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "path": request.path,
            "raw_path": request.path.encode(),
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 0),
            "server": ("127.0.0.1", 0),
        }

        # Create response holder
        response_data = {}
        response_status = None
        response_headers = None

        # Define receive function
        async def receive():
            return {
                "type": "http.request",
                "body": json.dumps(request.body).encode() if request.body else b"",
                "more_body": False,
            }

        # Define send function
        async def send(message):
            nonlocal response_data, response_status, response_headers
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message["headers"]
            elif message["type"] == "http.response.body":
                if message["body"]:
                    response_data = json.loads(message["body"])

        # Call ASGI application
        await self.app(scope, receive, send)

        return {
            "status": response_status,
            "headers": dict(response_headers) if response_headers else {},
            "body": response_data
        }

    async def process_line(self, line: str) -> None:
        """
        Process a single line of input.

        Args:
            line: Input line (JSON-encoded request)
        """
        try:
            # Parse request
            data = json.loads(line)
            request = StdioRequest(**data)

            # Handle request
            response = await self.handle_request(request)

            # Send response
            print(json.dumps(response), flush=True)
        except Exception as e:
            # Send error response
            print(json.dumps({
                "status": 500,
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