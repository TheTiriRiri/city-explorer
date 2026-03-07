"""Router for city photos endpoint."""

import httpx
import structlog
from fastapi import APIRouter, Depends, Path, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client
from app.models.photos import Photo, PhotosResponse
from app.services.photos_service import get_city_photos
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["photos"])
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/city/{city_name}/photos",
    response_model=PhotosResponse,
)
@limiter.limit("60/minute")
async def city_photos(
    request: Request,
    city_name: str = Path(..., description="City name"),
    limit: int = Query(12, ge=1, le=50, description="Max number of photos"),
    category: str = Query("all", description="Filter by category: architecture, nature, streets, other, all"),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
) -> PhotosResponse:
    """Return photos of a city from Wikimedia Commons."""
    cache_key = f"city_explorer:photos:{city_name}"
    cached = await cache_get(cache_key)

    if cached is not None:
        photos = [Photo(**p) for p in cached]
    else:
        try:
            photos = await get_city_photos(client, city_name, limit=limit)
        except Exception:
            logger.warning("photos_fetch_failed", city_name=city_name, exc_info=True)
            photos = []
        await cache_set(
            cache_key,
            [p.model_dump(mode="json") for p in photos],
            settings.cache_ttl_photos,
        )

    if category != "all":
        photos = [p for p in photos if p.category == category]

    return PhotosResponse(
        city=city_name,
        photos=photos[:limit],
        total=len(photos),
    )
