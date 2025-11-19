"""
Production-Ready Cache Utility

Provides a flexible caching system with support for Redis and in-memory caching.
Includes cache invalidation, TTL management, and decorators for easy usage.
"""

import json
import pickle
import hashlib
from typing import Any, Optional, Callable, Union
from functools import wraps
import asyncio

try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from app.core.utils import logger
from app.config.config import settings


class CacheConfig:
    """Cache configuration."""

    CACHE_ENABLED: bool = getattr(settings, "CACHE_ENABLED", True)
    CACHE_TYPE: str = getattr(settings, "CACHE_TYPE", "redis")  # 'redis' or 'memory'
    REDIS_URL: str = getattr(settings, "REDIS_URL", "redis://localhost:6379")
    CACHE_DEFAULT_TTL: int = getattr(settings, "CACHE_DEFAULT_TTL", 300)  # 5 minutes
    CACHE_KEY_PREFIX: str = getattr(settings, "CACHE_KEY_PREFIX", "app:cache:")


class InMemoryCache:
    """Simple in-memory cache implementation."""

    def __init__(self):
        self._cache = {}
        self._expiry = {}

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            # Check if expired
            if key in self._expiry:
                import time

                if time.time() > self._expiry[key]:
                    await self.delete(key)
                    return None
            return self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL."""
        self._cache[key] = value
        if ttl:
            import time

            self._expiry[key] = time.time() + ttl
        return True

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        self._cache.pop(key, None)
        self._expiry.pop(key, None)
        return True

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        return key in self._cache

    async def clear(self) -> bool:
        """Clear all cache."""
        self._cache.clear()
        self._expiry.clear()
        return True

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        import re

        regex = re.compile(pattern.replace("*", ".*"))
        keys_to_delete = [key for key in self._cache.keys() if regex.match(key)]
        for key in keys_to_delete:
            await self.delete(key)
        return len(keys_to_delete)


class RedisCache:
    """Redis cache implementation."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False,  # Handle binary data
            )
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        try:
            client = await self._get_client()
            value = await client.get(key)
            if value:
                return pickle.loads(value)
            return None
        except Exception as e:
            logger.log_error({"event": "cache_get_error", "key": key, "error": str(e)})
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in Redis cache with optional TTL."""
        try:
            client = await self._get_client()
            serialized = pickle.dumps(value)

            if ttl:
                await client.setex(key, ttl, serialized)
            else:
                await client.set(key, serialized)
            return True
        except Exception as e:
            logger.log_error({"event": "cache_set_error", "key": key, "error": str(e)})
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        try:
            client = await self._get_client()
            await client.delete(key)
            return True
        except Exception as e:
            logger.log_error(
                {"event": "cache_delete_error", "key": key, "error": str(e)}
            )
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache."""
        try:
            client = await self._get_client()
            return await client.exists(key) > 0
        except Exception as e:
            logger.log_error(
                {"event": "cache_exists_error", "key": key, "error": str(e)}
            )
            return False

    async def clear(self) -> bool:
        """Clear all cache (use with caution in production)."""
        try:
            client = await self._get_client()
            await client.flushdb()
            return True
        except Exception as e:
            logger.log_error({"event": "cache_clear_error", "error": str(e)})
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        try:
            client = await self._get_client()
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await client.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.log_error(
                {
                    "event": "cache_delete_pattern_error",
                    "pattern": pattern,
                    "error": str(e),
                }
            )
            return 0

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter in cache."""
        try:
            client = await self._get_client()
            return await client.incrby(key, amount)
        except Exception as e:
            logger.log_error(
                {"event": "cache_increment_error", "key": key, "error": str(e)}
            )
            return None

    async def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL for a key."""
        try:
            client = await self._get_client()
            return await client.ttl(key)
        except Exception as e:
            logger.log_error(
                {"event": "cache_get_ttl_error", "key": key, "error": str(e)}
            )
            return None

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()


class CacheManager:
    """Main cache manager with automatic backend selection."""

    def __init__(self):
        self._backend = None
        self._initialized = False

    async def _initialize(self):
        """Initialize cache backend."""
        if self._initialized:
            return

        if not CacheConfig.CACHE_ENABLED:
            logger.log_info({"event": "cache_disabled"})
            self._backend = InMemoryCache()  # Fallback to memory
            self._initialized = True
            return

        if CacheConfig.CACHE_TYPE == "redis" and REDIS_AVAILABLE:
            try:
                self._backend = RedisCache(CacheConfig.REDIS_URL)
                # Test connection
                await self._backend.set("__test__", "ok", ttl=10)
                await self._backend.delete("__test__")
                logger.log_info({"event": "cache_initialized", "backend": "redis"})
            except Exception as e:
                logger.log_warning(
                    {
                        "event": "redis_connection_failed",
                        "error": str(e),
                        "fallback": "memory",
                    }
                )
                self._backend = InMemoryCache()
        else:
            self._backend = InMemoryCache()
            logger.log_info({"event": "cache_initialized", "backend": "memory"})

        self._initialized = True

    def _make_key(self, key: str) -> str:
        """Create cache key with prefix."""
        return f"{CacheConfig.CACHE_KEY_PREFIX}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        await self._initialize()
        cache_key = self._make_key(key)
        return await self._backend.get(cache_key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache."""
        await self._initialize()
        cache_key = self._make_key(key)
        ttl = ttl or CacheConfig.CACHE_DEFAULT_TTL
        return await self._backend.set(cache_key, value, ttl)

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        await self._initialize()
        cache_key = self._make_key(key)
        return await self._backend.delete(cache_key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        await self._initialize()
        cache_key = self._make_key(key)
        return await self._backend.exists(cache_key)

    async def clear(self) -> bool:
        """Clear all cache."""
        await self._initialize()
        return await self._backend.clear()

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        await self._initialize()
        cache_pattern = self._make_key(pattern)
        return await self._backend.delete_pattern(cache_pattern)

    async def get_or_set(
        self, key: str, factory: Callable, ttl: Optional[int] = None
    ) -> Any:
        """
        Get value from cache, or compute and cache it.

        Args:
            key: Cache key
            factory: Function to compute value if not in cache
            ttl: Time to live in seconds

        Returns:
            Cached or computed value
        """
        value = await self.get(key)
        if value is not None:
            return value

        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        # Cache it
        await self.set(key, value, ttl)
        return value

    def generate_key(self, *args, **kwargs) -> str:
        """
        Generate cache key from function arguments.

        Example:
            key = cache.generate_key("users", user_id=123, active=True)
            # Returns: "users:user_id=123:active=True"
        """
        parts = [str(arg) for arg in args]
        parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return ":".join(parts)

    def make_hash_key(self, data: Union[str, dict, list]) -> str:
        """
        Create a hash-based cache key from data.

        Useful for caching based on complex data structures.
        """
        if isinstance(data, (dict, list)):
            data = json.dumps(data, sort_keys=True)
        return hashlib.md5(str(data).encode()).hexdigest()


# Global cache instance
cache = CacheManager()


def cached(
    ttl: Optional[int] = None,
    key_prefix: str = "",
    key_builder: Optional[Callable] = None,
):
    """
    Decorator to cache function results.

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
        key_builder: Custom function to build cache key

    Example:
        @cached(ttl=300, key_prefix="user")
        async def get_user(user_id: int):
            return await db.get(User, user_id)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default key builder
                func_name = f"{func.__module__}.{func.__name__}"
                arg_key = cache.generate_key(*args, **kwargs)
                cache_key = (
                    f"{key_prefix}:{func_name}:{arg_key}"
                    if key_prefix
                    else f"{func_name}:{arg_key}"
                )

            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.log_debug({"event": "cache_hit", "key": cache_key})
                return cached_value

            # Compute value
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Cache result
            await cache.set(cache_key, result, ttl)

            logger.log_debug({"event": "cache_miss", "key": cache_key})

            return result

        return wrapper

    return decorator


def cache_invalidate(*keys: str):
    """
    Decorator to invalidate cache keys after function execution.

    Example:
        @cache_invalidate("user:*", "users:list")
        async def update_user(user_id: int, data: dict):
            return await db.update(User, user_id, data)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Invalidate cache keys
            for key in keys:
                if "*" in key:
                    await cache.delete_pattern(key)
                else:
                    await cache.delete(key)

            logger.log_debug({"event": "cache_invalidated", "keys": keys})

            return result

        return wrapper

    return decorator
