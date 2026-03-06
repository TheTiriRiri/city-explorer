"""Redis caching decorator with graceful fallback."""

import functools
import json
from typing import Any, Callable

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

# Global Redis client reference, set by dependencies.py
_redis_client: Redis | None = None


def set_redis_client(client: Redis | None) -> None:
    """Set the global Redis client for use by the cache decorator."""
    global _redis_client
    _redis_client = client


def get_redis_client() -> Redis | None:
    """Get the global Redis client."""
    return _redis_client


async def cache_get(key: str) -> Any | None:
    """Get a value from Redis cache, returning None on failure."""
    if _redis_client is None:
        return None
    try:
        value = await _redis_client.get(key)
        if value is not None:
            return json.loads(value)
    except Exception:
        logger.warning("cache_get_failed", key=key, exc_info=True)
    return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """Set a value in Redis cache, silently failing on error."""
    if _redis_client is None:
        return
    try:
        serialized = json.dumps(value, default=str)
        await _redis_client.setex(key, ttl, serialized)
    except Exception:
        logger.warning("cache_set_failed", key=key, exc_info=True)


def cached(ttl: int, key_builder: Callable[..., str] | None = None):
    """Decorator that caches async function results in Redis.

    Args:
        ttl: Time-to-live in seconds for the cached value.
        key_builder: Optional callable that receives the same args as the
            decorated function and returns the cache key string. If not
            provided, a default key is built from function name and args.

    The decorator gracefully degrades when Redis is unavailable -- it
    simply calls the underlying function without caching.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Build cache key
            if key_builder is not None:
                cache_key = key_builder(*args, **kwargs)
            else:
                parts = [func.__module__, func.__qualname__]
                parts.extend(str(a) for a in args)
                parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = ":".join(parts)

            # Try cache read
            cached_value = await cache_get(cache_key)
            if cached_value is not None:
                logger.debug("cache_hit", key=cache_key)
                return cached_value

            # Cache miss -- call the actual function
            logger.debug("cache_miss", key=cache_key)
            result = await func(*args, **kwargs)

            # Store in cache
            if result is not None:
                # Convert pydantic models to dicts for serialization
                serializable = _make_serializable(result)
                await cache_set(cache_key, serializable, ttl)

            return result

        return wrapper

    return decorator


def _make_serializable(obj: Any) -> Any:
    """Convert pydantic models and other objects to JSON-serializable form."""
    from pydantic import BaseModel

    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    return obj
