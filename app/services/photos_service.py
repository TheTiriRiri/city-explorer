"""Wikimedia Commons photo service for city images."""

import re

import httpx
import structlog

from app.models.photos import Photo

logger = structlog.get_logger(__name__)

COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"

_CATEGORY_KEYWORDS = {
    "architecture": ["building", "church", "cathedral", "castle", "tower", "palace", "house", "facade", "architecture"],
    "nature": ["park", "garden", "river", "lake", "mountain", "forest", "tree", "nature", "landscape"],
    "streets": ["street", "road", "square", "avenue", "bridge", "market", "plaza"],
}


def _classify_photo(title: str, description: str) -> str:
    """Classify a photo into a category based on title and description keywords."""
    text = f"{title} {description}".lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return "other"


async def _fetch_category_members(
    client: httpx.AsyncClient,
    category: str,
    limit: int = 20,
) -> list[str]:
    """Fetch file titles from a Wikimedia Commons category."""
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmtype": "file",
        "cmlimit": str(limit),
        "format": "json",
    }
    try:
        response = await client.get(COMMONS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        members = data.get("query", {}).get("categorymembers", [])
        return [m["title"] for m in members]
    except httpx.HTTPError as exc:
        logger.warning("commons_category_request_failed", category=category, error=str(exc))
        return []


async def _fetch_image_info(
    client: httpx.AsyncClient,
    titles: list[str],
) -> list[Photo]:
    """Fetch image metadata (URL, thumbnail, description) for a list of file titles."""
    if not titles:
        return []

    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime",
        "iiurlwidth": "300",
        "format": "json",
    }
    try:
        response = await client.get(COMMONS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("commons_imageinfo_request_failed", error=str(exc))
        return []

    photos: list[Photo] = []
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        imageinfo = page.get("imageinfo", [])
        if not imageinfo:
            continue
        info = imageinfo[0]
        title = page.get("title", "")
        extmetadata = info.get("extmetadata", {})
        description = extmetadata.get("ImageDescription", {}).get("value", "") or ""
        # Strip HTML tags from description
        clean_desc = re.sub(r"<[^>]+>", "", description).strip()
        if len(clean_desc) > 300:
            clean_desc = clean_desc[:297] + "..."

        photo = Photo(
            title=title.replace("File:", ""),
            url=info.get("url", ""),
            thumbnail_url=info.get("thumburl"),
            description=clean_desc or None,
            category=_classify_photo(title, clean_desc),
            mime_type=info.get("mime"),
            commons_url=info.get("descriptionurl"),
        )
        photos.append(photo)
    return photos


async def get_city_photos(
    client: httpx.AsyncClient,
    city_name: str,
    limit: int = 12,
) -> list[Photo]:
    """Fetch photos of a city from Wikimedia Commons.

    Tries multiple category naming conventions with fallback.
    """
    log = logger.bind(city_name=city_name)

    # Try primary category
    titles = await _fetch_category_members(client, f"Category:{city_name}", limit)

    # Fallback: try {city}_city
    if not titles:
        log.info("commons_trying_fallback_category")
        titles = await _fetch_category_members(client, f"Category:{city_name}_city", limit)

    # Fallback: search in file namespace
    if not titles:
        log.info("commons_trying_search_fallback")
        params = {
            "action": "query",
            "list": "search",
            "srnamespace": "6",
            "srsearch": city_name,
            "srlimit": str(limit),
            "format": "json",
        }
        try:
            response = await client.get(COMMONS_API_URL, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("query", {}).get("search", [])
            titles = [r["title"] for r in results]
        except httpx.HTTPError as exc:
            log.warning("commons_search_failed", error=str(exc))

    if not titles:
        log.info("commons_no_photos_found")
        return []

    photos = await _fetch_image_info(client, titles[:limit])
    log.info("commons_photos_fetched", count=len(photos))
    return photos
