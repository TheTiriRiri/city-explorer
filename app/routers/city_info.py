"""Router for the city info aggregate endpoint."""

import asyncio

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client, get_shared_redis_client
from app.models.city_info import (
    CityDescription,
    CityInfo,
    ErrorResponse,
    FamousPerson,
    Weather,
)
from app.services.weather_service import get_weather
from app.services.wikipedia_service import get_city_description, get_famous_people
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["city-info"])
limiter = Limiter(key_func=get_remote_address)


async def _fetch_description_cached(
    client: httpx.AsyncClient,
    city_name: str,
    ttl: int,
) -> CityDescription:
    """Fetch city description with Redis caching."""
    cache_key = f"city_explorer:wiki:description:{city_name}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return CityDescription(**cached)

    result = await get_city_description(client, city_name)
    await cache_set(cache_key, result.model_dump(mode="json"), ttl)
    return result


async def _fetch_people_cached(
    client: httpx.AsyncClient,
    city_name: str,
    ttl: int,
) -> list[FamousPerson]:
    """Fetch famous people with Redis caching."""
    cache_key = f"city_explorer:wiki:people:{city_name}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return [FamousPerson(**p) for p in cached]

    result = await get_famous_people(client, city_name)
    await cache_set(
        cache_key,
        [p.model_dump(mode="json") for p in result],
        ttl,
    )
    return result


async def _fetch_weather_cached(
    client: httpx.AsyncClient,
    city_name: str,
    api_key: str,
    country_code: str | None,
    ttl: int,
) -> Weather:
    """Fetch weather with Redis caching."""
    cc = country_code or ""
    cache_key = f"city_explorer:weather:{city_name}:{cc}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return Weather(**cached)

    result = await get_weather(client, city_name, api_key, country_code)
    await cache_set(cache_key, result.model_dump(mode="json"), ttl)
    return result


async def _resolve_city_geo(
    client: httpx.AsyncClient,
    city_name: str,
    country_code: str | None,
    geonames_username: str,
) -> dict | None:
    """Try to resolve city coordinates and country via GeoNames.

    Returns a dict with keys: name, country, country_code, latitude, longitude.
    Returns None if lookup fails.
    """
    try:
        response = await client.get(
            "http://api.geonames.org/searchJSON",
            params={
                "q": city_name,
                "maxRows": 1,
                "featureClass": "P",
                "username": geonames_username,
                **({"country": country_code} if country_code else {}),
            },
        )
        response.raise_for_status()
        data = response.json()
        geonames = data.get("geonames", [])
        if geonames:
            hit = geonames[0]
            return {
                "name": hit.get("name", city_name),
                "country": hit.get("countryName", ""),
                "country_code": hit.get("countryCode", country_code or ""),
                "latitude": float(hit.get("lat", 0.0)),
                "longitude": float(hit.get("lng", 0.0)),
            }
    except Exception:
        logger.warning("geonames_city_lookup_failed", city_name=city_name, exc_info=True)
    return None


@router.get(
    "/city/{city_name}/info",
    response_model=CityInfo,
    responses={
        404: {"model": ErrorResponse, "description": "City not found"},
        503: {"model": ErrorResponse, "description": "Upstream services unavailable"},
    },
)
@limiter.limit("60/minute")
async def get_city_info(
    request: Request,
    city_name: str = Path(..., description="City name (URL-encoded if spaces)"),
    country_code: str | None = Query(
        None,
        description="Disambiguate cities with the same name (ISO 3166-1 alpha-2)",
    ),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
    redis: Redis | None = Depends(get_shared_redis_client),
) -> CityInfo:
    """Return full city profile: description, famous people, and current weather."""
    log = logger.bind(city_name=city_name, country_code=country_code)
    log.info("city_info_request_start")

    warnings: list[str] = []

    # ------------------------------------------------------------------
    # 1. Resolve city geography via GeoNames
    # ------------------------------------------------------------------
    geo = await _resolve_city_geo(
        client, city_name, country_code, settings.geonames_username
    )

    if geo is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CITY_NOT_FOUND",
                    "message": f"City '{city_name}' could not be found.",
                    "detail": None,
                }
            },
        )

    resolved_country = geo["country"]
    resolved_code = geo["country_code"]
    coordinates = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
    }

    # ------------------------------------------------------------------
    # 2. Fetch Wikipedia + Weather in parallel
    # ------------------------------------------------------------------
    description_task = _fetch_description_cached(
        client, city_name, settings.cache_ttl_wiki
    )
    people_task = _fetch_people_cached(
        client, city_name, settings.cache_ttl_wiki
    )
    weather_task = _fetch_weather_cached(
        client,
        city_name,
        settings.openweathermap_api_key,
        country_code,
        settings.cache_ttl_weather,
    )

    results = await asyncio.gather(
        description_task,
        people_task,
        weather_task,
        return_exceptions=True,
    )

    description_result, people_result, weather_result = results

    # ------------------------------------------------------------------
    # 3. Handle partial failures
    # ------------------------------------------------------------------
    description: CityDescription | None = None
    famous_people: list[FamousPerson] = []
    weather: Weather | None = None

    # Wikipedia description
    if isinstance(description_result, Exception):
        log.warning(
            "city_info_description_failed",
            error=str(description_result),
        )
        warnings.append("City description temporarily unavailable.")
    else:
        description = description_result

    # Famous people
    if isinstance(people_result, Exception):
        log.warning(
            "city_info_people_failed",
            error=str(people_result),
        )
        warnings.append("Famous people data temporarily unavailable.")
    else:
        famous_people = people_result

    # Weather
    if isinstance(weather_result, Exception):
        log.warning(
            "city_info_weather_failed",
            error=str(weather_result),
        )
        warnings.append("Weather data temporarily unavailable.")
    else:
        weather = weather_result

    # ------------------------------------------------------------------
    # 4. If ALL upstreams failed, return 503
    # ------------------------------------------------------------------
    if description is None and not famous_people and weather is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "UPSTREAM_ERROR",
                    "message": "All upstream data sources are currently unavailable.",
                    "detail": None,
                }
            },
        )

    # ------------------------------------------------------------------
    # 5. Build response
    # ------------------------------------------------------------------
    data_sources: dict[str, str] = {
        "description": "Wikipedia",
        "famous_people": "Wikipedia",
        "weather": "OpenWeatherMap",
    }

    city_info = CityInfo(
        city=geo["name"],
        country=resolved_country,
        country_code=resolved_code,
        coordinates=coordinates,
        description=description,
        famous_people=famous_people,
        weather=weather,
        data_sources=data_sources,
        warnings=warnings,
    )

    log.info("city_info_request_complete", warnings=warnings)
    return city_info
