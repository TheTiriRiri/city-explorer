"""Dependency injection: shared httpx.AsyncClient, Redis client, graceful fallback."""

import httpx
import structlog
from redis.asyncio import Redis

from app.config import settings
from app.utils.cache import get_redis_client, set_redis_client
from app.utils.http import get_http_client

logger = structlog.get_logger(__name__)


async def init_redis() -> Redis | None:
    """Initialise the Redis connection. Returns None if Redis is unavailable."""
    try:
        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        # Verify connectivity
        await client.ping()
        set_redis_client(client)
        logger.info("redis_connected", url=settings.redis_url)
        return client
    except Exception:
        logger.warning(
            "redis_unavailable",
            url=settings.redis_url,
            exc_info=True,
        )
        set_redis_client(None)
        return None


async def close_redis() -> None:
    """Close the Redis connection gracefully."""
    client = get_redis_client()
    if client is not None:
        await client.aclose()
        set_redis_client(None)
        logger.info("redis_closed")


def get_shared_http_client() -> httpx.AsyncClient:
    """FastAPI dependency that returns the shared httpx.AsyncClient."""
    return get_http_client()


def get_shared_redis_client() -> Redis | None:
    """FastAPI dependency that returns the shared Redis client (or None)."""
    return get_redis_client()
