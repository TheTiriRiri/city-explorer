"""Pytest fixtures: test app, async test client, mocked Redis, mocked httpx."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
import respx
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Return a Settings instance with test-appropriate defaults."""
    return Settings(
        app_env="testing",
        app_port=8000,
        log_level="DEBUG",
        redis_url="redis://localhost:6379/1",
        openweathermap_api_key="test_key",
        geonames_username="test_user",
        cache_ttl_countries=60,
        cache_ttl_cities=60,
        cache_ttl_wiki=60,
        cache_ttl_weather=60,
    )


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Return a mocked async Redis client.

    The mock behaves like a cache that always misses (get returns None)
    by default.  Tests can override return values as needed.
    """
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.aclose = AsyncMock(return_value=None)
    return redis_mock


@pytest.fixture
def _patch_redis(mock_redis: AsyncMock):
    """Patch the global Redis client used by the cache module."""
    with patch("app.utils.cache._redis_client", mock_redis), \
         patch("app.dependencies.get_redis_client", return_value=mock_redis):
        yield mock_redis


@pytest.fixture
def respx_mock():
    """Activate respx mocking so external HTTP calls are intercepted."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest_asyncio.fixture
async def async_client(_patch_redis, respx_mock) -> AsyncClient:
    """Provide an async httpx test client wired to the FastAPI app.

    Redis is mocked (always-miss cache) and external HTTP calls can be
    intercepted via respx in individual tests.
    """
    # Import app inside fixture to ensure patches are in place
    from app.main import app
    from app.utils.http import create_http_client, close_http_client

    # Create the shared HTTP client for the app
    create_http_client()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await close_http_client()


@pytest.fixture
def sync_client(_patch_redis) -> TestClient:
    """Provide a synchronous test client for simple endpoint tests."""
    from app.main import app

    with TestClient(app) as client:
        yield client
