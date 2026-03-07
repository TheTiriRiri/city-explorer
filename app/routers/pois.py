"""Router for city points of interest endpoint."""

import httpx
import structlog
from fastapi import APIRouter, Depends, Path, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client
from app.models.poi import POIResponse, PointOfInterest
from app.services.poi_service import get_city_pois
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["pois"])
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/city/{city_name}/pois",
    response_model=POIResponse,
)
@limiter.limit("60/minute")
async def city_pois(
    request: Request,
    city_name: str = Path(..., description="City name"),
    lat: float = Query(..., description="Latitude of city center"),
    lon: float = Query(..., description="Longitude of city center"),
    category: str = Query("all", description="Filter by category: museum, attraction, monument, park, religious, restaurant, all"),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
) -> POIResponse:
    """Return points of interest near a city from OpenStreetMap."""
    cache_key = f"city_explorer:pois:{lat:.4f}:{lon:.4f}"
    cached = await cache_get(cache_key)

    if cached is not None:
        pois = [PointOfInterest(**p) for p in cached]
    else:
        pois = await get_city_pois(client, lat, lon)
        await cache_set(
            cache_key,
            [p.model_dump(mode="json") for p in pois],
            settings.cache_ttl_pois,
        )

    if category != "all":
        pois = [p for p in pois if p.category == category]

    return POIResponse(
        city=city_name,
        pois=pois,
        total=len(pois),
    )
