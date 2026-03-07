"""Router for the random city discovery endpoint."""

import random

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client
from app.models.random_city import Coordinates, RandomCityResponse
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["random-city"])
limiter = Limiter(key_func=get_remote_address)

GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"

CONTINENT_CODE_MAP: dict[str, str] = {
    "Europe": "EU",
    "Asia": "AS",
    "Africa": "AF",
    "North America": "NA",
    "South America": "SA",
    "Oceania": "OC",
    "Antarctica": "AN",
}


async def _search_cities(
    client: httpx.AsyncClient,
    region: str | None,
    min_population: int | None,
    max_population: int | None,
) -> list[dict]:
    """Search GeoNames for cities matching the given criteria, with caching."""
    # Build cache key from filter params
    cache_parts = [
        f"region={region or 'all'}",
        f"minpop={min_population or 0}",
        f"maxpop={max_population or 'none'}",
    ]
    cache_key = f"city_explorer:random_cities:{':'.join(cache_parts)}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params: dict = {
        "featureClass": "P",
        "maxRows": 1000,
        "username": settings.geonames_username,
        "orderby": "population",
    }

    if region:
        continent_code = CONTINENT_CODE_MAP.get(region)
        if continent_code is None:
            raise ValueError(f"Invalid region: {region}")
        params["continentCode"] = continent_code

    if min_population is not None:
        # GeoNames does not support minPopulation directly in searchJSON,
        # but we can filter client-side. However, we can use cities endpoint
        # style param. Actually GeoNames searchJSON does not have minPopulation.
        # We'll filter results after fetching.
        pass

    try:
        response = await client.get(GEONAMES_SEARCH_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.error("random_city_http_error", status_code=response.status_code)
        raise
    except httpx.RequestError as exc:
        logger.error("random_city_request_error", url=str(exc.request.url), exc_info=True)
        raise

    data = response.json()

    if "status" in data:
        error_message = data["status"].get("message", "Unknown GeoNames error")
        logger.error("random_city_api_error", geonames_error=error_message)
        raise ValueError(f"GeoNames API error: {error_message}")

    geonames = data.get("geonames", [])

    # Client-side population filtering
    results = []
    for item in geonames:
        pop = int(item["population"]) if item.get("population") else None
        if min_population is not None and (pop is None or pop < min_population):
            continue
        if max_population is not None and (pop is None or pop > max_population):
            continue
        results.append(item)

    await cache_set(cache_key, results, settings.cache_ttl_cities)
    return results


@router.get(
    "/city/random",
    response_model=RandomCityResponse,
    responses={
        400: {"description": "Invalid region name"},
        404: {"description": "No cities match the given criteria"},
    },
)
@limiter.limit("60/minute")
async def get_random_city(
    request: Request,
    region: str | None = Query(
        None,
        description="Continent name (e.g. Europe, Asia, Africa, North America, South America, Oceania, Antarctica)",
    ),
    min_population: int | None = Query(
        None,
        ge=0,
        description="Minimum population filter",
    ),
    max_population: int | None = Query(
        None,
        ge=0,
        description="Maximum population filter",
    ),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
) -> RandomCityResponse:
    """Return a random city matching the given criteria."""
    log = logger.bind(region=region, min_population=min_population, max_population=max_population)
    log.info("random_city_request_start")

    # Validate region
    if region is not None and region not in CONTINENT_CODE_MAP:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REGION",
                    "message": f"Invalid region '{region}'. Valid regions: {', '.join(sorted(CONTINENT_CODE_MAP.keys()))}.",
                    "detail": None,
                }
            },
        )

    try:
        cities = await _search_cities(client, region, min_population, max_population)
    except Exception:
        log.error("random_city_search_failed", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "UPSTREAM_ERROR",
                    "message": "Failed to fetch city data from GeoNames.",
                    "detail": None,
                }
            },
        )

    if not cities:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NO_CITIES_FOUND",
                    "message": "No cities match the given criteria.",
                    "detail": None,
                }
            },
        )

    chosen = random.choice(cities)

    tz_info = chosen.get("timezone")
    timezone_id = tz_info.get("timeZoneId") if isinstance(tz_info, dict) else None
    raw_pop = chosen.get("population")
    population = int(raw_pop) if raw_pop else None

    result = RandomCityResponse(
        city=chosen.get("name", "Unknown"),
        country=chosen.get("countryName", ""),
        country_code=chosen.get("countryCode", ""),
        coordinates=Coordinates(
            latitude=float(chosen.get("lat", 0.0)),
            longitude=float(chosen.get("lng", 0.0)),
        ),
        population=population,
        timezone=timezone_id,
        data_sources={"geography": "GeoNames"},
    )

    log.info("random_city_request_complete", city=result.city)
    return result
