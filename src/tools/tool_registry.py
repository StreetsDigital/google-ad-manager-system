"""Tool Registry for MCP Server.

This module provides a registry system for managing and executing tools in the MCP server.
"""
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints, Union
import inspect
from functools import wraps
from pydantic import BaseModel, create_model

class ToolMetadata(BaseModel):
    """Metadata for a registered tool."""
    name: str
    description: str
    parameters: Dict[str, str]  # Changed from Dict[str, Any] to Dict[str, str] to store type names
    return_type: str  # Changed from Any to str to store type name
    handler: Callable

    def model_dump(self, **kwargs):
        """Override model_dump to exclude handler and convert types to strings."""
        data = super().model_dump(**kwargs)
        data.pop('handler', None)
        return data

class ToolRegistry:
    """Registry for managing MCP tools."""
    
    def __init__(self):
        """Initialize an empty tool registry."""
        self.tools: Dict[str, ToolMetadata] = {}
    
    def register(self, name: str, description: str = "") -> Callable:
        """Register a tool with the registry.
        
        Args:
            name: Unique name for the tool
            description: Optional description of the tool's functionality
            
        Returns:
            Decorator function to wrap the tool handler
            
        Raises:
            ValueError: If a tool with the same name is already registered
        """
        def decorator(func: Callable) -> Callable:
            if name in self.tools:
                raise ValueError(f"Tool '{name}' is already registered")
            
            # Extract parameter types and return type
            sig = inspect.signature(func)
            type_hints = get_type_hints(func)
            
            parameters = {
                param.name: str(type_hints.get(param.name, Any))
                for param in sig.parameters.values()
                if param.name != 'self'  # Skip self parameter for methods
            }
            
            return_type = str(type_hints.get('return', Any))
            
            # Create metadata
            metadata = ToolMetadata(
                name=name,
                description=description or func.__doc__ or "",
                parameters=parameters,
                return_type=return_type,
                handler=func
            )
            
            self.tools[name] = metadata
            return func
            
        return decorator
    
    def get_tool(self, name: str) -> Callable:
        """Get a registered tool by name.
        
        Args:
            name: Name of the tool to retrieve
            
        Returns:
            The tool's handler function
            
        Raises:
            KeyError: If no tool with the given name exists
        """
        if name not in self.tools:
            raise KeyError(f"No tool registered with name '{name}'")
        return self.tools[name].handler
    
    def list_tools(self) -> List[str]:
        """List all registered tool names.
        
        Returns:
            List of registered tool names
        """
        return list(self.tools.keys())
    
    def get_tool_metadata(self, name: str) -> ToolMetadata:
        """Get metadata for a registered tool.
        
        Args:
            name: Name of the tool
            
        Returns:
            Metadata for the specified tool
            
        Raises:
            KeyError: If no tool with the given name exists
        """
        if name not in self.tools:
            raise KeyError(f"No tool registered with name '{name}'")
        return self.tools[name]

def auto_tool(registry: ToolRegistry, name: Optional[str] = None, description: str = ""):
    """Decorator to automatically register a function as a tool.
    
    Args:
        registry: The tool registry to register with
        name: Optional name for the tool (defaults to function name)
        description: Optional description of the tool
        
    Returns:
        Decorator function that registers and wraps the tool handler
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
            
        # Register the wrapped function
        registry.register(tool_name, description)(wrapper)
        return wrapper
        
    return decorator 