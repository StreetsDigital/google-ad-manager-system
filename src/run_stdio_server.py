#!/usr/bin/env python3
"""
Run the MCP server with STDIO interface.

This script starts the FastAPI application with a STDIO interface
for command-line interaction.
"""

from .main import app
from .mcp.server.stdio import create_stdio_server

def main():
    """Run the STDIO server."""
    server = create_stdio_server(app)
    server.run()

if __name__ == "__main__":
    main() 