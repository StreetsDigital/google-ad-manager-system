"""
Application configuration.

This module provides centralized configuration management using Pydantic.
"""

from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

class RedisConfig(BaseModel):
    """Redis configuration."""
    url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    prefix: str = Field(default="gaas:", env="REDIS_PREFIX")
    
    # Key prefixes
    flow_prefix: str = "flow:"
    token_prefix: str = "token:"
    rate_limit_prefix: str = "rate:"

class AuthConfig(BaseModel):
    """Authentication configuration."""
    token_expiry: int = Field(default=86400, env="TOKEN_EXPIRY")  # 24 hours
    flow_expiry: int = Field(default=3600, env="FLOW_EXPIRY")  # 1 hour
    client_config_path: str = Field(default="client_config.json", env="CLIENT_CONFIG_PATH")

class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""
    window: int = Field(default=60, env="RATE_LIMIT_WINDOW")  # 1 minute
    max_requests: int = Field(default=100, env="RATE_LIMIT_MAX_REQUESTS")

class BatchConfig(BaseModel):
    """Batch operation configuration."""
    max_size: int = Field(default=100, env="BATCH_MAX_SIZE")
    concurrent_limit: int = Field(default=3, env="BATCH_CONCURRENT_LIMIT")
    timeout: int = Field(default=300, env="BATCH_TIMEOUT")  # 5 minutes

class NetworkConfig(BaseModel):
    """Network configuration."""
    retry_count: int = Field(default=3, env="NETWORK_RETRY_COUNT")
    retry_delay: int = Field(default=1, env="NETWORK_RETRY_DELAY")
    timeout: int = Field(default=30, env="NETWORK_TIMEOUT")
    pool_size: int = Field(default=10, env="NETWORK_POOL_SIZE")

class ServerConfig(BaseModel):
    """Server configuration."""
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    debug: bool = Field(default=False, env="DEBUG")
    cors_origins: list[str] = Field(default=["*"], env="CORS_ORIGINS")

class Settings(BaseSettings):
    """Application settings."""
    redis: RedisConfig = RedisConfig()
    auth: AuthConfig = AuthConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    batch: BatchConfig = BatchConfig()
    network: NetworkConfig = NetworkConfig()
    server: ServerConfig = ServerConfig()
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Create global settings instance
settings = Settings()

# Export individual configs for convenience
redis_config = settings.redis
auth_config = settings.auth
rate_limit_config = settings.rate_limit
batch_config = settings.batch
network_config = settings.network
server_config = settings.server 