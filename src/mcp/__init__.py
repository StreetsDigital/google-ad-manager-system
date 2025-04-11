"""
MCP (Model Control Protocol) module.

This module provides the implementation of the Model Control Protocol,
which enables standardized interaction with AI models.
"""

from .server.fastmcp import FastMCPServer

__all__ = ['FastMCPServer']
