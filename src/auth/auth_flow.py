"""
OAuth2 authentication flow implementation for Google Ad Manager.

This module provides a complete OAuth2 authentication flow implementation,
including token management, refresh logic, and state tracking.
"""

from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import json
import os
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

# Configure logging
logger = logging.getLogger(__name__)

class AuthState(BaseModel):
    """Authentication state model."""
    is_authenticated: bool = Field(default=False, description="Whether client is authenticated")
    token_expiry: Optional[datetime] = Field(default=None, description="Token expiration timestamp")
    last_refresh: Optional[datetime] = Field(default=None, description="Last token refresh timestamp")
    error: Optional[str] = Field(default=None, description="Last authentication error")

class ClientConfig(BaseModel):
    """Client configuration model."""
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    auth_uri: str = Field(default="https://accounts.google.com/o/oauth2/auth", description="Authorization endpoint")
    token_uri: str = Field(default="https://oauth2.googleapis.com/token", description="Token endpoint")
    redirect_uris: list[str] = Field(default=["http://localhost"], description="Redirect URIs")

class AuthFlow:
    """Manages OAuth2 authentication flow for Google Ad Manager."""
    
    def __init__(self, 
                 client_config: Union[str, Dict[str, Any], ClientConfig],
                 token_path: str = 'token.json'):
        """
        Initialize authentication flow manager.
        
        Args:
            client_config: Either a path to config JSON file, a dict with config data,
                         or a ClientConfig instance
            token_path: Path to save/load token
        """
        self.token_path = token_path
        self.credentials: Optional[Credentials] = None
        self.state = AuthState()
        
        # Initialize client configuration
        self._init_client_config(client_config)
    
    def _init_client_config(self, client_config: Union[str, Dict[str, Any], ClientConfig]) -> None:
        """Initialize client configuration from various input types."""
        try:
            if isinstance(client_config, str):
                # Load from file path
                with open(client_config, 'r') as f:
                    config_data = json.load(f)
                    self.client_config = self._parse_config_dict(config_data)
            elif isinstance(client_config, dict):
                # Use direct dictionary input
                self.client_config = self._parse_config_dict(client_config)
            elif isinstance(client_config, ClientConfig):
                # Use ClientConfig instance directly
                self.client_config = client_config
            else:
                raise ValueError("client_config must be a file path, dict, or ClientConfig instance")
                
        except Exception as e:
            logger.error(f"Failed to initialize client configuration: {e}")
            self.state.error = f"Configuration error: {str(e)}"
            raise
    
    def _parse_config_dict(self, config_data: Dict[str, Any]) -> ClientConfig:
        """Parse configuration dictionary into ClientConfig model."""
        try:
            # Handle Google OAuth client configuration format
            if 'web' in config_data:
                web_config = config_data['web']
                return ClientConfig(
                    client_id=web_config['client_id'],
                    client_secret=web_config['client_secret'],
                    auth_uri=web_config.get('auth_uri'),
                    token_uri=web_config.get('token_uri'),
                    redirect_uris=web_config.get('redirect_uris', ["http://localhost"])
                )
            # Handle direct configuration format
            return ClientConfig(**config_data)
        except Exception as e:
            raise ValueError(f"Invalid configuration format: {str(e)}")
    
    async def update_client_config(self, 
                                 new_config: Union[Dict[str, Any], ClientConfig]
                                 ) -> AuthState:
        """
        Update client configuration with new values.
        
        Args:
            new_config: New configuration as dict or ClientConfig instance
            
        Returns:
            Updated authentication state
        """
        try:
            if isinstance(new_config, dict):
                self.client_config = self._parse_config_dict(new_config)
            elif isinstance(new_config, ClientConfig):
                self.client_config = new_config
            else:
                raise ValueError("new_config must be a dict or ClientConfig instance")
            
            # Reset credentials since config changed
            self.credentials = None
            self.state.is_authenticated = False
            self.state.error = None
            
            return self.state
            
        except Exception as e:
            logger.error(f"Failed to update client configuration: {e}")
            self.state.error = f"Configuration update error: {str(e)}"
            return self.state
    
    async def update_credentials(self, 
                               token_data: Dict[str, Any]
                               ) -> AuthState:
        """
        Update credentials with new token data.
        
        Args:
            token_data: Dictionary containing token information
            
        Returns:
            Updated authentication state
        """
        try:
            self.credentials = Credentials.from_authorized_user_info(
                token_data,
                scopes=['https://www.googleapis.com/auth/dfp']
            )
            
            if self.credentials.expired:
                await self.refresh_token()
            else:
                self.state.is_authenticated = True
                self.state.token_expiry = datetime.fromtimestamp(self.credentials.expiry.timestamp())
                self.state.error = None
                await self.save_token()
            
            return self.state
            
        except Exception as e:
            logger.error(f"Failed to update credentials: {e}")
            self.state.error = f"Credentials update error: {str(e)}"
            self.state.is_authenticated = False
            return self.state
    
    async def initialize(self) -> AuthState:
        """
        Initialize authentication state.
        
        Returns:
            Current authentication state
        """
        try:
            if os.path.exists(self.token_path):
                await self.load_token()
            return self.state
        except Exception as e:
            self.state.error = f"Initialization error: {str(e)}"
            logger.error(f"Failed to initialize auth flow: {e}")
            return self.state
    
    async def load_token(self) -> None:
        """Load and validate existing token."""
        try:
            with open(self.token_path, 'r') as token_file:
                token_data = json.load(token_file)
                self.credentials = Credentials.from_authorized_user_info(
                    token_data,
                    scopes=['https://www.googleapis.com/auth/dfp']
                )
                
                if self.credentials.expired:
                    await self.refresh_token()
                else:
                    self.state.is_authenticated = True
                    self.state.token_expiry = datetime.fromtimestamp(self.credentials.expiry.timestamp())
                    
        except Exception as e:
            logger.error(f"Failed to load token: {e}")
            self.state.error = f"Token load error: {str(e)}"
            self.credentials = None
    
    async def refresh_token(self) -> bool:
        """
        Refresh the access token if possible.
        
        Returns:
            bool: True if refresh was successful, False otherwise
        """
        try:
            if not self.credentials or not self.credentials.refresh_token:
                return False
                
            self.credentials.refresh(Request())
            await self.save_token()
            
            self.state.is_authenticated = True
            self.state.token_expiry = datetime.fromtimestamp(self.credentials.expiry.timestamp())
            self.state.last_refresh = datetime.now()
            self.state.error = None
            
            return True
            
        except RefreshError as e:
            logger.error(f"Token refresh failed: {e}")
            self.state.error = f"Refresh error: {str(e)}"
            self.state.is_authenticated = False
            return False
    
    async def start_flow(self) -> AuthState:
        """
        Start OAuth2 flow to obtain new credentials.
        
        Returns:
            Updated authentication state
        """
        try:
            flow = InstalledAppFlow.from_client_config(
                client_config=self.client_config,
                scopes=['https://www.googleapis.com/auth/dfp']
            )
            
            self.credentials = flow.run_local_server(port=0)
            await self.save_token()
            
            self.state.is_authenticated = True
            self.state.token_expiry = datetime.fromtimestamp(self.credentials.expiry.timestamp())
            self.state.last_refresh = datetime.now()
            self.state.error = None
            
            return self.state
            
        except Exception as e:
            logger.error(f"OAuth flow failed: {e}")
            self.state.error = f"OAuth flow error: {str(e)}"
            self.state.is_authenticated = False
            return self.state
    
    async def save_token(self) -> None:
        """Save current token to file."""
        if not self.credentials:
            return
            
        try:
            token_data = {
                'token': self.credentials.token,
                'refresh_token': self.credentials.refresh_token,
                'token_uri': self.credentials.token_uri,
                'client_id': self.credentials.client_id,
                'client_secret': self.credentials.client_secret,
                'scopes': self.credentials.scopes
            }
            
            with open(self.token_path, 'w') as token_file:
                json.dump(token_data, token_file)
                
        except Exception as e:
            logger.error(f"Failed to save token: {e}")
            self.state.error = f"Token save error: {str(e)}"
    
    def get_credentials(self) -> Optional[Credentials]:
        """
        Get current credentials.
        
        Returns:
            Optional[Credentials]: Current credentials or None if not authenticated
        """
        return self.credentials if self.state.is_authenticated else None
    
    def get_state(self) -> AuthState:
        """
        Get current authentication state.
        
        Returns:
            AuthState: Current authentication state
        """
        return self.state 