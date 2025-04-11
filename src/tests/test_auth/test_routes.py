"""
Tests for authentication routes.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import json
from datetime import datetime, timedelta
import time
import redis
from src.auth.routes import (
    auth_router, redis_client, FLOW_EXPIRY, TOKEN_EXPIRY,
    RATE_LIMIT_PREFIX, FLOW_PREFIX, TOKEN_PREFIX, RateLimitMiddleware, RATE_LIMIT_WINDOW, RATE_LIMIT_MAX_REQUESTS
)
from src.main import app
from google.oauth2.credentials import Credentials
from fastapi import Request

app.include_router(auth_router)
client = TestClient(app)

@pytest.fixture
def valid_config():
    """Valid client configuration."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "scopes": ["https://www.googleapis.com/auth/dfp"]
    }

@pytest.fixture
def mock_flow():
    """Create a mock flow that can be JSON serialized."""
    flow = MagicMock()
    flow.client_config = {
        "installed": {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "redirect_uris": ["http://localhost:8000/auth/callback"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    flow.oauth2session.scope = ["https://www.googleapis.com/auth/dfp"]
    flow.redirect_uri = "http://localhost:8000/auth/callback"
    flow.authorization_url.return_value = ("http://example.com/auth", "test_state")
    flow.credentials = MagicMock()
    flow.credentials.token = "test_token"
    flow.credentials.refresh_token = "test_refresh_token"
    flow.credentials.expiry = datetime.now() + timedelta(hours=1)
    flow.credentials.token_uri = "https://oauth2.googleapis.com/token"
    return flow

@pytest.fixture
def mock_credentials():
    """Create a mock credentials object."""
    with patch("google.oauth2.credentials.Credentials") as mock_creds_class:
        mock_creds = mock_creds_class.return_value
        mock_creds.token = "new_token"
        mock_creds.refresh_token = "new_refresh_token"
        mock_creds.expiry = datetime.now() + timedelta(hours=1)
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "test_client_id"
        mock_creds.client_secret = "test_client_secret"
        mock_creds.scopes = ["https://www.googleapis.com/auth/dfp"]
        
        def mock_refresh(request):
            mock_creds.token = "refreshed_token"
            mock_creds.expiry = datetime.now() + timedelta(hours=1)
        
        mock_creds.refresh = mock_refresh
        yield mock_creds

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("src.auth.routes.redis_client") as mock_client:
        # Mock rate limiting - allow requests by default
        def get_side_effect(key):
            if key.startswith(RATE_LIMIT_PREFIX):
                return None  # No rate limit by default
            elif key.startswith(TOKEN_PREFIX):
                stored_token = {
                    "token": "test_token",
                    "refresh_token": "test_refresh_token",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": "test_client_id",
                    "client_secret": "test_client_secret",
                    "scopes": ["https://www.googleapis.com/auth/dfp"],
                    "expiry": int((datetime.now() + timedelta(hours=1)).timestamp())
                }
                return json.dumps(stored_token)
            return None
            
        mock_client.get.side_effect = get_side_effect
        mock_client.setex.return_value = True
        mock_client.incr.return_value = 1
        mock_client.ttl.return_value = 60
        mock_client.pipeline.return_value = MagicMock(
            incr=lambda key: None,
            expire=lambda key, time: None,
            execute=lambda: [1, True]
        )
        
        yield mock_client

@pytest.fixture
def test_app():
    """Create a test FastAPI app with rate limiting middleware."""
    from fastapi import FastAPI
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.include_router(auth_router)
    
    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}
        
    return app

@pytest.fixture
def test_client(test_app, mock_redis):
    """Test client with auth router and rate limiting middleware."""
    return TestClient(test_app)

@pytest.fixture
def test_client_with_middleware(test_app):
    """Create a test client with rate limiting middleware for rate limit tests."""
    return TestClient(test_app)

@pytest.fixture
def mock_auth_flow():
    """Mock AuthFlow."""
    with patch("src.auth.routes.AuthFlow") as mock:
        instance = mock.return_value
        instance.start_flow = AsyncMock(return_value="https://example.com/auth")
        instance.exchange_code = AsyncMock(return_value={
            "token": "test_token",
            "refresh_token": "test_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/dfp"]
        })
        yield instance

class TestAuthRoutes:
    """Test cases for authentication routes."""

    def test_initialize_auth_success(self, mock_redis, mock_auth_flow):
        """Test successful auth flow initialization."""
        response = client.post("/auth/init")
        assert response.status_code == 200
        data = response.json()
        assert "flow_id" in data
        assert data["auth_url"] == "https://example.com/auth"
        assert data["expires_in"] == FLOW_EXPIRY

        # Verify Redis storage
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0].startswith(FLOW_PREFIX)
        assert call_args[1] == FLOW_EXPIRY

    def test_auth_callback_success(self, mock_redis, mock_auth_flow):
        """Test successful auth callback."""
        # Mock flow retrieval
        mock_redis.get.return_value = json.dumps({
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        })

        response = client.get("/auth/callback?code=test_code&state=test_state")
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == TOKEN_EXPIRY
        assert data["refresh_token"] == "test_refresh_token"

        # Verify token storage
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0].startswith(TOKEN_PREFIX)
        assert call_args[1] == TOKEN_EXPIRY

    def test_auth_callback_invalid_state(self, mock_redis):
        """Test auth callback with invalid state."""
        mock_redis.get.return_value = None
        response = client.get("/auth/callback?code=test_code&state=invalid")
        assert response.status_code == 404
        assert "Flow not found or expired" in response.json()["detail"]

    def test_refresh_token_success(self, mock_redis, mock_credentials):
        """Test successful token refresh."""
        # Mock token retrieval
        mock_redis.get.return_value = json.dumps({
            "token": "old_token",
            "refresh_token": "old_refresh_token"
        })

        response = client.post(
            "/auth/refresh",
            headers={"Authorization": "Bearer test_token"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == TOKEN_EXPIRY
        assert data["refresh_token"] == "test_refresh_token"

        # Verify new token storage
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0].startswith(TOKEN_PREFIX)
        assert call_args[1] == TOKEN_EXPIRY

    def test_refresh_token_invalid(self, mock_redis):
        """Test token refresh with invalid token."""
        mock_redis.get.return_value = None
        response = client.post(
            "/auth/refresh",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401
        assert "Invalid or expired token" in response.json()["detail"]

    def test_revoke_token_success(self, mock_redis, mock_credentials):
        """Test successful token revocation."""
        # Mock token retrieval
        mock_redis.get.return_value = json.dumps({
            "token": "test_token",
            "refresh_token": "test_refresh_token"
        })

        response = client.post(
            "/auth/revoke",
            headers={"Authorization": "Bearer test_token"}
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Token revoked successfully"

        # Verify token deletion
        mock_redis.delete.assert_called_once()
        call_args = mock_redis.delete.call_args[0]
        assert call_args[0].startswith(TOKEN_PREFIX)

    def test_introspect_token_success(self, mock_redis, mock_credentials):
        """Test successful token introspection."""
        # Mock token retrieval
        mock_redis.get.return_value = json.dumps({
            "token": "test_token",
            "refresh_token": "test_refresh_token"
        })

        response = client.get(
            "/auth/introspect",
            headers={"Authorization": "Bearer test_token"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["scope"] == "https://www.googleapis.com/auth/dfp"
        assert data["client_id"] == "test_client_id"
        assert "expires_at" in data
        assert "issued_at" in data

    def test_rate_limiting(self, mock_redis):
        """Test rate limiting middleware."""
        # Mock rate limit counter
        mock_redis.get.side_effect = [None] + [str(i) for i in range(1, 101)]
        mock_redis.setex.return_value = True
        mock_redis.incr.return_value = 1

        # Make requests up to limit
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            response = client.post("/auth/init")
            assert response.status_code != 429

        # Next request should be rate limited
        response = client.post("/auth/init")
        assert response.status_code == 429
        assert "Too many requests" in response.json()["detail"]

def test_init_auth_flow_success(test_client, valid_config, mock_flow):
    """Test successful initialization of auth flow."""
    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config") as mock_from_config:
        mock_from_config.return_value = mock_flow
        response = test_client.post("/auth/init", json=valid_config)
        
        assert response.status_code == 200
        assert "auth_url" in response.json()
        assert "flow_id" in response.json()

def test_init_auth_flow_invalid_config(test_client, mock_redis):
    """Test initialization with invalid config."""
    response = test_client.post("/auth/init", json={})
    assert response.status_code == 422

def test_auth_callback_invalid_code(test_client, mock_flow, mock_redis):
    """Test callback with invalid code."""
    flow_id = "test_flow_id"
    
    # Mock flow storage
    flow_data = {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "scopes": ["https://www.googleapis.com/auth/dfp"],
        "redirect_uri": "http://localhost:8000/auth/callback",
        "state": flow_id
    }
    mock_redis.get.side_effect = lambda key: (
        json.dumps(flow_data).encode() if key == f"{FLOW_PREFIX}{flow_id}" else None
    )
    
    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config") as mock_from_config:
        mock_from_config.return_value = mock_flow
        mock_flow.fetch_token.side_effect = ValueError("Invalid code")
        
        response = test_client.get(f"/auth/callback?code=invalid_code&state={flow_id}")
        assert response.status_code == 400
        assert "Invalid authorization code" in response.json()["detail"]

def test_refresh_token_invalid_token(test_client, mock_redis):
    """Test refresh with invalid token."""
    mock_redis.get.return_value = None
    response = test_client.post("/auth/refresh", json={
        "refresh_token": "invalid_token",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret"
    })
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_rate_limit_middleware(test_app):
    """Test that rate limiting works correctly."""
    with patch("src.auth.routes.redis_client") as mock_redis:
        # Mock Redis methods for sequential requests
        mock_redis.get.side_effect = [None] * RATE_LIMIT_MAX_REQUESTS + ["10"]
        mock_redis.setex.return_value = True
        mock_redis.incr.side_effect = range(1, RATE_LIMIT_MAX_REQUESTS + 2)
        mock_redis.ttl.return_value = RATE_LIMIT_WINDOW
        mock_redis.pipeline.return_value = MagicMock(
            incr=lambda key: None,
            expire=lambda key, time: None,
            execute=lambda: [1, True]
        )
        
        test_client = TestClient(test_app)
        
        # Make MAX_REQUESTS requests (should all succeed)
        responses = []
        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            response = test_client.get("/test")
            responses.append(response.status_code)
        
        assert all(status == 200 for status in responses)
        
        # Next request should be rate limited
        response = test_client.get("/test")
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"] 