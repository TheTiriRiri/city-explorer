"""OpenStreetMap Overpass API service for points of interest."""

import math

import httpx
import structlog

from app.models.poi import PointOfInterest

logger = structlog.get_logger(__name__)

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

_OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:25];
(
  node["tourism"~"museum|attraction|viewpoint"](around:{radius},{lat},{lon});
  node["historic"~"monument|memorial|castle"](around:{radius},{lat},{lon});
  node["leisure"="park"](around:{radius},{lat},{lon});
  node["amenity"~"place_of_worship|restaurant"](around:{radius},{lat},{lon});
  way["tourism"~"museum|attraction|viewpoint"](around:{radius},{lat},{lon});
  way["historic"~"monument|memorial|castle"](around:{radius},{lat},{lon});
  way["leisure"="park"](around:{radius},{lat},{lon});
);
out center 100;
"""

_TAG_TO_CATEGORY = {
    "museum": "museum",
    "attraction": "attraction",
    "viewpoint": "attraction",
    "monument": "monument",
    "memorial": "monument",
    "castle": "monument",
    "park": "park",
    "place_of_worship": "religious",
    "restaurant": "restaurant",
}


def _classify_element(tags: dict) -> str:
    """Determine the POI category from OSM tags."""
    for key in ("tourism", "historic", "leisure", "amenity"):
        value = tags.get(key, "")
        if value in _TAG_TO_CATEGORY:
            return _TAG_TO_CATEGORY[value]
    return "other"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def get_city_pois(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    radius: int = 5000,
) -> list[PointOfInterest]:
    """Fetch points of interest near given coordinates from Overpass API.

    Args:
        client: Shared httpx async client.
        lat: Latitude of city center.
        lon: Longitude of city center.
        radius: Search radius in meters (default 5000m = 5km).

    Returns:
        A list of up to 50 PointOfInterest models, sorted by distance.
    """
    log = logger.bind(lat=lat, lon=lon, radius=radius)

    query = _OVERPASS_QUERY_TEMPLATE.format(radius=radius, lat=lat, lon=lon)

    try:
        response = await client.post(
            OVERPASS_API_URL,
            data={"data": query},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        log.warning("overpass_request_failed", error=str(exc))
        return []

    elements = data.get("elements", [])
    pois: list[PointOfInterest] = []

    for elem in elements:
        tags = elem.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        # For ways, use center coordinates
        if elem["type"] == "way":
            center = elem.get("center", {})
            elem_lat = center.get("lat")
            elem_lon = center.get("lon")
        else:
            elem_lat = elem.get("lat")
            elem_lon = elem.get("lon")

        if elem_lat is None or elem_lon is None:
            continue

        distance = _haversine_km(lat, lon, elem_lat, elem_lon)

        poi = PointOfInterest(
            name=name,
            category=_classify_element(tags),
            latitude=elem_lat,
            longitude=elem_lon,
            distance_km=round(distance, 2),
            osm_type=elem["type"],
            osm_id=elem.get("id"),
        )
        pois.append(poi)

    # Sort by distance, limit to 50
    pois.sort(key=lambda p: p.distance_km or 0)
    pois = pois[:50]

    log.info("overpass_pois_fetched", count=len(pois))
    return pois
