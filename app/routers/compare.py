"""Router for the city comparison endpoint."""

import asyncio

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client
from app.models.city_info import Weather
from app.models.compare import CityComparisonEntry, CityComparisonResponse
from app.services.weather_service import get_weather
from app.services.wikipedia_service import get_famous_people
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["compare"])
limiter = Limiter(key_func=get_remote_address)

_MAX_CITIES = 5


async def _resolve_city_geo(
    client: httpx.AsyncClient,
    city_name: str,
) -> dict | None:
    """Resolve city geography via GeoNames (population, timezone, country)."""
    try:
        response = await client.get(
            "http://api.geonames.org/searchJSON",
            params={
                "q": city_name,
                "maxRows": 1,
                "featureClass": "P",
                "username": settings.geonames_username,
            },
        )
        response.raise_for_status()
        data = response.json()
        geonames = data.get("geonames", [])
        if geonames:
            hit = geonames[0]
            tz_info = hit.get("timezone")
            return {
                "name": hit.get("name", city_name),
                "country": hit.get("countryName", ""),
                "country_code": hit.get("countryCode", ""),
                "population": int(hit["population"]) if hit.get("population") else None,
                "timezone": tz_info.get("timeZoneId") if isinstance(tz_info, dict) else None,
            }
    except Exception:
        logger.warning("compare_geonames_failed", city_name=city_name, exc_info=True)
    return None


async def _fetch_weather_cached(
    client: httpx.AsyncClient,
    city_name: str,
) -> Weather | None:
    """Fetch weather with caching, return None on failure."""
    cache_key = f"city_explorer:weather:{city_name}:"
    cached = await cache_get(cache_key)
    if cached is not None:
        return Weather(**cached)
    try:
        result = await get_weather(
            client, city_name, settings.openweathermap_api_key,
        )
        await cache_set(cache_key, result.model_dump(mode="json"), settings.cache_ttl_weather)
        return result
    except Exception:
        logger.warning("compare_weather_failed", city_name=city_name, exc_info=True)
        return None


async def _fetch_people_count_cached(
    client: httpx.AsyncClient,
    city_name: str,
) -> int:
    """Fetch famous people count with caching, return 0 on failure."""
    cache_key = f"city_explorer:wiki:people:{city_name}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return len(cached)
    try:
        people = await get_famous_people(client, city_name)
        await cache_set(
            cache_key,
            [p.model_dump(mode="json") for p in people],
            settings.cache_ttl_wiki,
        )
        return len(people)
    except Exception:
        logger.warning("compare_people_failed", city_name=city_name, exc_info=True)
        return 0


async def _build_entry(
    client: httpx.AsyncClient,
    city_name: str,
) -> CityComparisonEntry | None:
    """Build comparison data for a single city."""
    geo = await _resolve_city_geo(client, city_name)
    if geo is None:
        return None

    warnings: list[str] = []

    weather, people_count = await asyncio.gather(
        _fetch_weather_cached(client, city_name),
        _fetch_people_count_cached(client, city_name),
    )

    if weather is None:
        warnings.append("Weather data temporarily unavailable.")

    return CityComparisonEntry(
        city=geo["name"],
        country=geo["country"],
        country_code=geo["country_code"],
        population=geo["population"],
        timezone=geo["timezone"],
        weather=weather,
        famous_people_count=people_count,
        warnings=warnings,
    )


@router.get(
    "/cities/compare",
    response_model=CityComparisonResponse,
)
@limiter.limit("60/minute")
async def compare_cities(
    request: Request,
    cities: str = Query(
        ...,
        description="Comma-separated list of city names (2-5 cities)",
        examples=["Kraków,Warszawa,Gdańsk"],
    ),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
) -> CityComparisonResponse:
    """Compare multiple cities side by side: weather, population, timezone, famous people count."""
    city_names = [c.strip() for c in cities.split(",") if c.strip()]

    if len(city_names) < 2:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "TOO_FEW_CITIES",
                    "message": "At least 2 cities are required for comparison.",
                    "detail": None,
                }
            },
        )

    if len(city_names) > _MAX_CITIES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "TOO_MANY_CITIES",
                    "message": f"At most {_MAX_CITIES} cities can be compared at once.",
                    "detail": None,
                }
            },
        )

    logger.info("compare_request_start", cities=city_names)

    tasks = [_build_entry(client, name) for name in city_names]
    results = await asyncio.gather(*tasks)

    entries = [r for r in results if r is not None]

    if not entries:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NO_CITIES_FOUND",
                    "message": "None of the requested cities could be found.",
                    "detail": None,
                }
            },
        )

    logger.info("compare_request_complete", found=len(entries), requested=len(city_names))

    return CityComparisonResponse(
        cities=entries,
        data_sources={
            "geography": "GeoNames",
            "weather": "OpenWeatherMap",
            "famous_people": "Wikipedia",
        },
    )
