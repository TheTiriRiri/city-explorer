"""Router for country-related endpoints."""

import httpx
import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client, get_shared_redis_client
from app.models.country import CountriesResponse, Country
from app.services import countries_service
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["countries"])
limiter = Limiter(key_func=get_remote_address)

CACHE_KEY_ALL_COUNTRIES = "city_explorer:countries:all"


async def _get_all_countries(
    client: httpx.AsyncClient,
    redis: Redis | None,
) -> list[Country]:
    """Return the full countries list, using Redis cache when available."""
    cached = await cache_get(CACHE_KEY_ALL_COUNTRIES)
    if cached is not None:
        logger.debug("countries_cache_hit")
        return [Country(**item) for item in cached]

    logger.debug("countries_cache_miss")
    countries = await countries_service.fetch_all_countries(client)

    # Store in cache as list of dicts
    await cache_set(
        CACHE_KEY_ALL_COUNTRIES,
        [c.model_dump(mode="json") for c in countries],
        settings.cache_ttl_countries,
    )
    return countries


@router.get(
    "/countries",
    response_model=CountriesResponse,
    responses={
        503: {
            "description": "Upstream service unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "UPSTREAM_ERROR",
                            "message": "Unable to fetch countries from upstream service.",
                            "detail": None,
                        }
                    }
                }
            },
        }
    },
)
@limiter.limit("60/minute")
async def list_countries(
    request: Request,
    search: str | None = Query(
        None,
        description="Filter countries by name (case-insensitive partial match)",
    ),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
    redis: Redis | None = Depends(get_shared_redis_client),
) -> CountriesResponse | JSONResponse:
    """Return a list of all available countries, optionally filtered by name."""
    try:
        countries = await _get_all_countries(client, redis)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("countries_upstream_error", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "UPSTREAM_ERROR",
                    "message": "Unable to fetch countries from upstream service.",
                    "detail": str(exc),
                }
            },
        )

    # Apply optional search filter in-memory
    if search:
        search_lower = search.lower()
        countries = [c for c in countries if search_lower in c.name.lower()]

    return CountriesResponse(count=len(countries), countries=countries)
