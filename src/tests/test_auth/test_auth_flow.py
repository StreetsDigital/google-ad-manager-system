"""Tests for the OAuth2 authentication flow implementation."""

import pytest
from datetime import datetime, timedelta
import json
import os
from unittest.mock import Mock, patch, ANY
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

from auth.auth_flow import AuthFlow, AuthState, ClientConfig

# Test data
SAMPLE_CLIENT_CONFIG = {
    'client_id': 'test-client-id',
    'client_secret': 'test-client-secret',
    'auth_uri': 'https://test.auth.uri',
    'token_uri': 'https://test.token.uri',
    'redirect_uris': ['http://localhost:8080']
}

SAMPLE_TOKEN_DATA = {
    'token': 'test-token',
    'refresh_token': 'test-refresh-token',
    'token_uri': 'https://test.token.uri',
    'client_id': 'test-client-id',
    'client_secret': 'test-client-secret',
    'scopes': ['https://www.googleapis.com/auth/dfp']
}

@pytest.fixture
def mock_credentials():
    """Create mock credentials for testing."""
    creds = Mock(spec=Credentials)
    creds.expired = False
    creds.expiry = datetime.now() + timedelta(hours=1)
    creds.token = 'test-token'
    creds.refresh_token = 'test-refresh-token'
    return creds

@pytest.fixture
def auth_flow(tmp_path):
    """Create AuthFlow instance with test configuration."""
    config_path = tmp_path / "client_config.json"
    with open(config_path, 'w') as f:
        json.dump({'web': SAMPLE_CLIENT_CONFIG}, f)
    return AuthFlow(str(config_path), token_path=str(tmp_path / "token.json"))

class TestAuthFlow:
    """Test cases for AuthFlow class."""
    
    def test_init_with_file_path(self, tmp_path):
        """Test initialization with config file path."""
        config_path = tmp_path / "client_config.json"
        with open(config_path, 'w') as f:
            json.dump({'web': SAMPLE_CLIENT_CONFIG}, f)
            
        auth_flow = AuthFlow(str(config_path))
        assert isinstance(auth_flow.client_config, ClientConfig)
        assert auth_flow.client_config.client_id == SAMPLE_CLIENT_CONFIG['client_id']
        
    def test_init_with_dict(self):
        """Test initialization with config dictionary."""
        auth_flow = AuthFlow(SAMPLE_CLIENT_CONFIG)
        assert isinstance(auth_flow.client_config, ClientConfig)
        assert auth_flow.client_config.client_id == SAMPLE_CLIENT_CONFIG['client_id']
        
    def test_init_with_client_config(self):
        """Test initialization with ClientConfig instance."""
        config = ClientConfig(**SAMPLE_CLIENT_CONFIG)
        auth_flow = AuthFlow(config)
        assert auth_flow.client_config == config
        
    def test_init_with_invalid_input(self):
        """Test initialization with invalid input."""
        with pytest.raises(ValueError):
            AuthFlow(123)  # Invalid type
            
    @pytest.mark.asyncio
    async def test_update_client_config_with_dict(self, auth_flow):
        """Test updating client config with dictionary."""
        new_config = {
            'client_id': 'new-client-id',
            'client_secret': 'new-client-secret',
            'redirect_uris': ['http://localhost:9000']
        }
        
        state = await auth_flow.update_client_config(new_config)
        assert state.is_authenticated is False  # Should reset auth state
        assert auth_flow.client_config.client_id == 'new-client-id'
        assert auth_flow.credentials is None
        
    @pytest.mark.asyncio
    async def test_update_client_config_with_model(self, auth_flow):
        """Test updating client config with ClientConfig instance."""
        new_config = ClientConfig(
            client_id='new-client-id',
            client_secret='new-client-secret'
        )
        
        state = await auth_flow.update_client_config(new_config)
        assert state.is_authenticated is False
        assert auth_flow.client_config == new_config
        
    @pytest.mark.asyncio
    async def test_update_credentials_valid(self, auth_flow, mock_credentials):
        """Test updating credentials with valid token data."""
        with patch('google.oauth2.credentials.Credentials.from_authorized_user_info',
                  return_value=mock_credentials):
            state = await auth_flow.update_credentials(SAMPLE_TOKEN_DATA)
            
        assert state.is_authenticated is True
        assert state.error is None
        assert state.token_expiry is not None
        
    @pytest.mark.asyncio
    async def test_update_credentials_expired(self, auth_flow, mock_credentials):
        """Test updating credentials with expired token."""
        mock_credentials.expired = True
        
        with patch('google.oauth2.credentials.Credentials.from_authorized_user_info',
                  return_value=mock_credentials), \
             patch.object(auth_flow, 'refresh_token', return_value=True):
            state = await auth_flow.update_credentials(SAMPLE_TOKEN_DATA)
            
        assert state.is_authenticated is True
        assert state.error is None
        
    @pytest.mark.asyncio
    async def test_update_credentials_invalid(self, auth_flow):
        """Test updating credentials with invalid token data."""
        invalid_token = {'token': 'invalid'}
        state = await auth_flow.update_credentials(invalid_token)
        
        assert state.is_authenticated is False
        assert state.error is not None
        
    @pytest.mark.asyncio
    async def test_refresh_token_success(self, auth_flow, mock_credentials):
        """Test successful token refresh."""
        auth_flow.credentials = mock_credentials
        mock_credentials.refresh = Mock()
        
        success = await auth_flow.refresh_token()
        
        assert success is True
        assert auth_flow.state.is_authenticated is True
        assert auth_flow.state.error is None
        mock_credentials.refresh.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_refresh_token_failure(self, auth_flow, mock_credentials):
        """Test failed token refresh."""
        auth_flow.credentials = mock_credentials
        mock_credentials.refresh = Mock(side_effect=RefreshError())
        
        success = await auth_flow.refresh_token()
        
        assert success is False
        assert auth_flow.state.is_authenticated is False
        assert auth_flow.state.error is not None 