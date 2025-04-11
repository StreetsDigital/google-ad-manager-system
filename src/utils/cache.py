"""
Redis-based caching implementation.

This module provides caching functionality using Redis with support for
key expiration, serialization, and cache invalidation.
"""

import json
import pickle
from typing import Any, Optional, Union
from datetime import datetime, timedelta
import redis
from functools import wraps

from src.config import redis_config
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

class Cache:
    """Redis cache implementation."""

    def __init__(self):
        """Initialize Redis connection."""
        self.redis = redis.from_url(
            redis_config.url,
            password=redis_config.password,
            decode_responses=True
        )
        self.binary_redis = redis.from_url(
            redis_config.url,
            password=redis_config.password,
            decode_responses=False
        )
        self.prefix = redis_config.prefix

    def _get_key(self, key: str) -> str:
        """
        Get prefixed cache key.

        Args:
            key: Original key

        Returns:
            str: Prefixed key
        """
        return f"{self.prefix}{key}"

    def get(self, key: str) -> Optional[str]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Optional[str]: Cached value if exists
        """
        try:
            return self.redis.get(self._get_key(key))
        except redis.RedisError as e:
            logger.error(f"Redis error in get: {e}")
            return None

    def get_json(self, key: str) -> Optional[Any]:
        """
        Get JSON value from cache.

        Args:
            key: Cache key

        Returns:
            Optional[Any]: Deserialized JSON value if exists
        """
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                return None
        return None

    def get_pickle(self, key: str) -> Optional[Any]:
        """
        Get pickled value from cache.

        Args:
            key: Cache key

        Returns:
            Optional[Any]: Deserialized pickled value if exists
        """
        try:
            value = self.binary_redis.get(self._get_key(key))
            if value:
                return pickle.loads(value)
            return None
        except (redis.RedisError, pickle.PickleError) as e:
            logger.error(f"Error in get_pickle: {e}")
            return None

    def set(
        self,
        key: str,
        value: str,
        expire: Optional[Union[int, timedelta]] = None
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            expire: Optional expiration time in seconds or timedelta

        Returns:
            bool: True if successful
        """
        try:
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())
            
            self.redis.set(self._get_key(key), value, ex=expire)
            return True
        except redis.RedisError as e:
            logger.error(f"Redis error in set: {e}")
            return False

    def set_json(
        self,
        key: str,
        value: Any,
        expire: Optional[Union[int, timedelta]] = None
    ) -> bool:
        """
        Set JSON value in cache.

        Args:
            key: Cache key
            value: Value to serialize and cache
            expire: Optional expiration time in seconds or timedelta

        Returns:
            bool: True if successful
        """
        try:
            return self.set(key, json.dumps(value), expire)
        except (TypeError, json.JSONEncodeError) as e:
            logger.error(f"JSON encode error: {e}")
            return False

    def set_pickle(
        self,
        key: str,
        value: Any,
        expire: Optional[Union[int, timedelta]] = None
    ) -> bool:
        """
        Set pickled value in cache.

        Args:
            key: Cache key
            value: Value to pickle and cache
            expire: Optional expiration time in seconds or timedelta

        Returns:
            bool: True if successful
        """
        try:
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())
            
            self.binary_redis.set(
                self._get_key(key),
                pickle.dumps(value),
                ex=expire
            )
            return True
        except (redis.RedisError, pickle.PickleError) as e:
            logger.error(f"Error in set_pickle: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            bool: True if successful
        """
        try:
            self.redis.delete(self._get_key(key))
            return True
        except redis.RedisError as e:
            logger.error(f"Redis error in delete: {e}")
            return False

    def clear_pattern(self, pattern: str) -> bool:
        """
        Delete all keys matching pattern.

        Args:
            pattern: Key pattern to match

        Returns:
            bool: True if successful
        """
        try:
            keys = self.redis.keys(self._get_key(pattern))
            if keys:
                self.redis.delete(*keys)
            return True
        except redis.RedisError as e:
            logger.error(f"Redis error in clear_pattern: {e}")
            return False

def cached(
    key_pattern: str,
    expire: Optional[Union[int, timedelta]] = None,
    use_pickle: bool = False
):
    """
    Cache decorator.

    Args:
        key_pattern: Pattern for cache key with {param} placeholders
        expire: Optional expiration time in seconds or timedelta
        use_pickle: Whether to use pickle serialization

    Returns:
        Callable: Decorated function
    """
    cache = Cache()
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from pattern and arguments
            bound_args = func.__annotations__.bind(*args, **kwargs)
            bound_args.apply_defaults()
            key = key_pattern.format(**bound_args.arguments)
            
            # Try to get from cache
            if use_pickle:
                result = cache.get_pickle(key)
            else:
                result = cache.get_json(key)
            
            if result is not None:
                return result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            
            if use_pickle:
                cache.set_pickle(key, result, expire)
            else:
                cache.set_json(key, result, expire)
            
            return result
        
        return wrapper
    
    return decorator 