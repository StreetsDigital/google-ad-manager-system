"""
Authentication routes for Google Ad Manager OAuth2 flow.

This module provides FastAPI routes for handling OAuth2 authentication flow,
including initialization, callback handling, token refresh, and status checks.
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, Dict, Any
import redis
import json
import secrets
from datetime import datetime, timedelta
import os
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

from .auth_flow import AuthFlow, AuthState, ClientConfig
from .errors import AuthError, ConfigError

# Configure Redis for session storage
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
redis_client = redis.from_url(REDIS_URL, password=REDIS_PASSWORD)

# Configure expiry times
FLOW_EXPIRY = int(os.getenv("FLOW_EXPIRY", 3600))  # 1 hour
TOKEN_EXPIRY = int(os.getenv("TOKEN_EXPIRY", 86400))  # 24 hours

# Redis key prefixes
FLOW_PREFIX = "oauth_flow:"
TOKEN_PREFIX = "token:"
RATE_LIMIT_PREFIX = "rate_limit:"

# Rate limiting configuration
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # 60 seconds
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", 100))  # 100 requests per window

# Create router
auth_router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth2 scheme for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Request/Response Models
class AuthInitResponse(BaseModel):
    """Response model for auth initialization."""
    flow_id: str
    auth_url: str
    expires_in: int

class TokenResponse(BaseModel):
    """Response model for token operations."""
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None

class TokenIntrospectResponse(BaseModel):
    """Response model for token introspection."""
    active: bool
    scope: Optional[str] = None
    client_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    issued_at: Optional[datetime] = None

# Middleware for rate limiting
class RateLimitMiddleware:
    """Rate limiting middleware."""
    
    async def __call__(self, request: Request, call_next):
        """Process the request with rate limiting."""
        client_ip = request.client.host
        key = f"{RATE_LIMIT_PREFIX}{client_ip}"
        
        # Get current request count
        current = redis_client.get(key)
        if current is None:
            redis_client.setex(key, RATE_LIMIT_WINDOW, 1)
        elif int(current) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=429,
                detail="Too many requests"
            )
        else:
            redis_client.incr(key)
        
        response = await call_next(request)
        return response

# Helper Functions
async def get_auth_flow(flow_id: str) -> AuthFlow:
    """Get AuthFlow instance from Redis."""
    flow_data = redis_client.get(f"{FLOW_PREFIX}{flow_id}")
    if not flow_data:
        raise HTTPException(
            status_code=404,
            detail="Flow not found or expired"
        )
    return AuthFlow(json.loads(flow_data))

async def get_current_token(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Get and validate current token."""
    token_data = redis_client.get(f"{TOKEN_PREFIX}{token}")
    if not token_data:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    return json.loads(token_data)

# Routes
@auth_router.post("/init", response_model=AuthInitResponse)
async def initialize_auth(request: Request):
    """Initialize OAuth2 flow."""
    try:
        # Generate flow ID
        flow_id = secrets.token_urlsafe(32)
        
        # Create auth flow
        flow = AuthFlow({
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": [str(request.url_for("auth_callback"))]
        })
        
        # Get authorization URL
        auth_url = await flow.start_flow()
        
        # Store flow in Redis
        redis_client.setex(
            f"{FLOW_PREFIX}{flow_id}",
            FLOW_EXPIRY,
            json.dumps(flow.client_config)
        )
        
        return AuthInitResponse(
            flow_id=flow_id,
            auth_url=auth_url,
            expires_in=FLOW_EXPIRY
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize auth flow: {str(e)}"
        )

@auth_router.get("/callback")
async def auth_callback(request: Request, code: str, state: str):
    """Handle OAuth2 callback."""
    try:
        # Get flow from state
        flow = await get_auth_flow(state)
        
        # Exchange code for token
        token_data = await flow.exchange_code(code)
        
        # Generate access token
        access_token = secrets.token_urlsafe(32)
        
        # Store token data
        redis_client.setex(
            f"{TOKEN_PREFIX}{access_token}",
            TOKEN_EXPIRY,
            json.dumps(token_data)
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=TOKEN_EXPIRY,
            refresh_token=token_data.get("refresh_token")
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Authentication failed: {str(e)}"
        )

@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(token_data: Dict[str, Any] = Depends(get_current_token)):
    """Refresh access token."""
    try:
        # Create credentials from token data
        credentials = Credentials.from_authorized_user_info(token_data)
        
        # Refresh token
        credentials.refresh(Request())
        
        # Generate new access token
        new_access_token = secrets.token_urlsafe(32)
        
        # Store new token data
        new_token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes
        }
        
        redis_client.setex(
            f"{TOKEN_PREFIX}{new_access_token}",
            TOKEN_EXPIRY,
            json.dumps(new_token_data)
        )
        
        return TokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=TOKEN_EXPIRY,
            refresh_token=credentials.refresh_token
        )
        
    except RefreshError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token refresh failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Token refresh failed: {str(e)}"
        )

@auth_router.post("/revoke")
async def revoke_token(token_data: Dict[str, Any] = Depends(get_current_token)):
    """Revoke access token."""
    try:
        # Create credentials from token data
        credentials = Credentials.from_authorized_user_info(token_data)
        
        # Revoke token
        credentials.revoke(Request())
        
        # Remove token from Redis
        redis_client.delete(f"{TOKEN_PREFIX}{token_data['token']}")
        
        return {"message": "Token revoked successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Token revocation failed: {str(e)}"
        )

@auth_router.get("/introspect", response_model=TokenIntrospectResponse)
async def introspect_token(token_data: Dict[str, Any] = Depends(get_current_token)):
    """Get token metadata."""
    try:
        # Create credentials from token data
        credentials = Credentials.from_authorized_user_info(token_data)
        
        return TokenIntrospectResponse(
            active=not credentials.expired,
            scope=" ".join(credentials.scopes),
            client_id=credentials.client_id,
            expires_at=credentials.expiry,
            issued_at=datetime.fromtimestamp(credentials.expiry.timestamp() - TOKEN_EXPIRY)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Token introspection failed: {str(e)}"
        ) 