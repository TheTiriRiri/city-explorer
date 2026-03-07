"""Router for city timeline endpoint."""

import httpx
import structlog
from fastapi import APIRouter, Depends, Path, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_shared_http_client
from app.models.timeline import HistoricalEvent, TimelineResponse
from app.services.timeline_service import get_city_timeline
from app.utils.cache import cache_get, cache_set

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["timeline"])
limiter = Limiter(key_func=get_remote_address)


@router.get(
    "/city/{city_name}/timeline",
    response_model=TimelineResponse,
)
@limiter.limit("60/minute")
async def city_timeline(
    request: Request,
    city_name: str = Path(..., description="City name"),
    client: httpx.AsyncClient = Depends(get_shared_http_client),
) -> TimelineResponse:
    """Return historical timeline events for a city from Wikipedia."""
    cache_key = f"city_explorer:timeline:{city_name}"
    cached = await cache_get(cache_key)

    if cached is not None:
        events = [HistoricalEvent(**e) for e in cached]
    else:
        try:
            events = await get_city_timeline(client, city_name)
        except Exception:
            logger.warning("timeline_fetch_failed", city_name=city_name, exc_info=True)
            events = []
        await cache_set(
            cache_key,
            [e.model_dump(mode="json") for e in events],
            settings.cache_ttl_wiki,
        )

    return TimelineResponse(
        city=city_name,
        events=events,
        total=len(events),
    )
