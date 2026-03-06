"""Shared async HTTP client helper."""

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Default timeout for all external API calls (5 seconds per PRD)
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=10.0)

# Global shared client, managed via app lifespan
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient.

    Raises RuntimeError if the client has not been initialised (i.e. the
    application lifespan has not started yet).
    """
    if _http_client is None:
        raise RuntimeError(
            "HTTP client not initialised. "
            "Ensure the application lifespan has started."
        )
    return _http_client


def create_http_client() -> httpx.AsyncClient:
    """Create and store a new shared httpx.AsyncClient."""
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "CityExplorerAPI/1.0"},
    )
    logger.info("http_client_created")
    return _http_client


async def close_http_client() -> None:
    """Close and discard the shared httpx.AsyncClient."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("http_client_closed")
