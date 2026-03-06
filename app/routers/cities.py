"""Router for city listing endpoints."""

import httpx
import structlog
from fastapi import APIRouter, Depends, Path, Query, Request
from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client, get_shared_redis_client
from app.models.city import CitiesResponse, City
from app.services import cities_service
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["cities"])
limiter = Limiter(key_func=get_remote_address)

# Maps country codes to country names. Populated on first request and reused.
_COUNTRY_NAME_CACHE: dict[str, str] = {}

_COUNTRY_NAME_URL = "https://restcountries.com/v3.1/alpha/{code}?fields=name"


async def _resolve_country_name(
    country_code: str,
    client: httpx.AsyncClient,
) -> str:
    """Resolve an ISO alpha-2 country code to its common name.

    Uses an in-process dict so repeated calls within the same process
    lifetime avoid extra HTTP round-trips.
    """
    if country_code in _COUNTRY_NAME_CACHE:
        return _COUNTRY_NAME_CACHE[country_code]

    try:
        resp = await client.get(
            _COUNTRY_NAME_URL.format(code=country_code),
        )
        resp.raise_for_status()
        data = resp.json()
        name = data.get("name", {}).get("common", country_code)
    except Exception:
        logger.warning(
            "country_name_resolve_failed",
            country_code=country_code,
            exc_info=True,
        )
        name = country_code

    _COUNTRY_NAME_CACHE[country_code] = name
    return name


@router.get("/countries/{country_code}/cities", response_model=CitiesResponse)
@limiter.limit("60/minute")
async def list_cities(
    request: Request,
    country_code: str = Path(
        ...,
        description="ISO 3166-1 alpha-2 country code (e.g. PL, US, DE)",
        min_length=2,
        max_length=2,
    ),
    search: str | None = Query(None, description="Filter cities by name"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
    redis: Redis | None = Depends(get_shared_redis_client),
) -> CitiesResponse:
    """Return a paginated list of cities for the given country code."""

    country_code = country_code.upper()
    cache_key = f"city_explorer:cities:{country_code}"

    # ------------------------------------------------------------------
    # 1. Try to load the full city list from Redis cache
    # ------------------------------------------------------------------
    cities: list[City] | None = None
    cached_data = await cache_get(cache_key)
    if cached_data is not None:
        try:
            cities = [City(**item) for item in cached_data]
            logger.debug("cities_cache_hit", country_code=country_code)
        except Exception:
            logger.warning(
                "cities_cache_parse_failed",
                country_code=country_code,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # 2. On cache miss, fetch from upstream GeoNames service
    # ------------------------------------------------------------------
    if cities is None:
        try:
            cities = await cities_service.fetch_cities_for_country(
                country_code=country_code,
                client=client,
                geonames_username=settings.geonames_username,
            )
        except ValueError as exc:
            from fastapi.responses import JSONResponse

            logger.warning(
                "cities_not_found",
                country_code=country_code,
                detail=str(exc),
            )
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "COUNTRY_NOT_FOUND",
                        "message": f"Country code '{country_code}' not found.",
                        "detail": str(exc),
                    }
                },
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            from fastapi.responses import JSONResponse

            logger.error(
                "cities_upstream_error",
                country_code=country_code,
                exc_info=True,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "UPSTREAM_ERROR",
                        "message": "Unable to fetch city data from upstream service.",
                        "detail": str(exc),
                    }
                },
            )

        # Store full (unfiltered) list in cache
        await cache_set(
            cache_key,
            [city.model_dump(mode="json") for city in cities],
            settings.cache_ttl_cities,
        )

    # ------------------------------------------------------------------
    # 3. Apply optional in-memory search filter
    # ------------------------------------------------------------------
    if search:
        search_lower = search.lower()
        cities = [c for c in cities if search_lower in c.name.lower()]

    # ------------------------------------------------------------------
    # 4. Pagination
    # ------------------------------------------------------------------
    total = len(cities)
    start = (page - 1) * per_page
    end = start + per_page
    page_cities = cities[start:end]

    # ------------------------------------------------------------------
    # 5. Resolve country name
    # ------------------------------------------------------------------
    country_name = await _resolve_country_name(country_code, client)

    return CitiesResponse(
        country_code=country_code,
        country_name=country_name,
        total=total,
        page=page,
        per_page=per_page,
        cities=page_cities,
    )
