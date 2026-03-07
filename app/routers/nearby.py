"""Router for the nearby cities endpoint."""

import math

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client
from app.models.nearby import Coordinates, NearbyCitiesResponse, NearbyCityEntry
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["nearby"])
limiter = Limiter(key_func=get_remote_address)

GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"
GEONAMES_FIND_NEARBY_URL = "http://api.geonames.org/findNearbyJSON"

_EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points using Haversine formula.

    Returns distance in kilometres.
    """
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


async def _resolve_origin(
    client: httpx.AsyncClient,
    city_name: str,
) -> dict | None:
    """Resolve the origin city via GeoNames searchJSON."""
    try:
        response = await client.get(
            GEONAMES_SEARCH_URL,
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
                "latitude": float(hit.get("lat", 0.0)),
                "longitude": float(hit.get("lng", 0.0)),
                "population": int(hit["population"]) if hit.get("population") else None,
                "timezone": tz_info.get("timeZoneId") if isinstance(tz_info, dict) else None,
                "geonameId": hit.get("geonameId"),
            }
    except Exception:
        logger.warning("nearby_origin_lookup_failed", city_name=city_name, exc_info=True)
    return None


async def _find_nearby_cities(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    radius_km: int,
    max_rows: int,
) -> list[dict]:
    """Find nearby cities using GeoNames searchJSON with lat/lng."""
    try:
        response = await client.get(
            GEONAMES_SEARCH_URL,
            params={
                "lat": str(lat),
                "lng": str(lng),
                "radius": str(radius_km),
                "maxRows": str(max_rows + 10),  # fetch extra to account for origin filtering
                "featureClass": "P",
                "cities": "cities5000",
                "username": settings.geonames_username,
                "orderby": "population",
            },
        )
        response.raise_for_status()
        data = response.json()
        return data.get("geonames", [])
    except Exception:
        logger.warning(
            "nearby_search_failed", lat=lat, lng=lng, radius_km=radius_km, exc_info=True
        )
        return []


@router.get(
    "/city/{city_name}/nearby",
    response_model=NearbyCitiesResponse,
    responses={
        404: {"description": "City not found"},
    },
)
@limiter.limit("60/minute")
async def get_nearby_cities(
    request: Request,
    city_name: str = Path(..., description="City name (URL-encoded if spaces)"),
    radius_km: int = Query(100, ge=1, le=500, description="Search radius in kilometres"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
) -> NearbyCitiesResponse:
    """Return cities within a given radius of the specified city."""
    log = logger.bind(city_name=city_name, radius_km=radius_km, limit=limit)
    log.info("nearby_request_start")

    # Check cache
    cache_key = f"city_explorer:nearby:{city_name}:{radius_km}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        log.info("nearby_cache_hit")
        return NearbyCitiesResponse(**cached)

    # Resolve origin city
    origin = await _resolve_origin(client, city_name)
    if origin is None:
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

    origin_lat = origin["latitude"]
    origin_lng = origin["longitude"]
    origin_geoname_id = origin.get("geonameId")

    # Find nearby cities
    raw_cities = await _find_nearby_cities(client, origin_lat, origin_lng, radius_km, limit)

    # Build entries, filtering out the origin city and applying Haversine
    entries: list[NearbyCityEntry] = []
    for city_data in raw_cities:
        geoname_id = city_data.get("geonameId")
        if geoname_id and geoname_id == origin_geoname_id:
            continue

        lat = float(city_data.get("lat", 0.0))
        lng = float(city_data.get("lng", 0.0))
        distance = haversine(origin_lat, origin_lng, lat, lng)

        if distance > radius_km:
            continue

        tz_info = city_data.get("timezone")
        raw_pop = city_data.get("population")

        entries.append(
            NearbyCityEntry(
                city=city_data.get("name", "Unknown"),
                country=city_data.get("countryName", ""),
                country_code=city_data.get("countryCode", ""),
                population=int(raw_pop) if raw_pop else None,
                timezone=tz_info.get("timeZoneId") if isinstance(tz_info, dict) else None,
                distance_km=round(distance, 2),
                coordinates=Coordinates(latitude=lat, longitude=lng),
            )
        )

    # Sort by distance, apply limit
    entries.sort(key=lambda e: e.distance_km)
    entries = entries[:limit]

    response = NearbyCitiesResponse(
        origin_city=origin["name"],
        origin_country=origin["country"],
        origin_coordinates=Coordinates(latitude=origin_lat, longitude=origin_lng),
        radius_km=radius_km,
        nearby_cities=entries,
        total=len(entries),
    )

    # Cache the result
    await cache_set(cache_key, response.model_dump(mode="json"), settings.cache_ttl_cities)

    log.info("nearby_request_complete", total=len(entries))
    return response
