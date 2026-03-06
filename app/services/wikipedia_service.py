"""Wikipedia service for city descriptions and famous people."""

import asyncio
import re

import httpx
import structlog

from app.models.city_info import CityDescription, FamousPerson

logger = structlog.get_logger(__name__)

WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_ACTION_API_URL = "https://en.wikipedia.org/w/api.php"

# Regex patterns for extracting birth/death years
# Matches patterns like "(1920-2005)", "(born 1920)", "(1920 - 2005)",
# "(born January 5, 1920)", "(1920 - present)"
_YEAR_RANGE_RE = re.compile(
    r"\((?:[^)]*?\b)?(\d{4})\s*[-\u2013]\s*(\d{4})\s*\)",
)
_BORN_YEAR_RE = re.compile(
    r"\(\s*born\s+(?:\w+\s+\d{1,2},?\s+)?(\d{4})\s*\)",
    re.IGNORECASE,
)
_BIRTH_DEATH_TEXT_RE = re.compile(
    r"(\d{4})\s*[-\u2013]\s*(\d{4})",
)
_SINGLE_BORN_RE = re.compile(
    r"\bborn\b[^.]*?(\d{4})",
    re.IGNORECASE,
)


def _parse_years(extract: str) -> tuple[int | None, int | None]:
    """Parse birth and death years from a Wikipedia extract string.

    Tries multiple regex patterns to handle varied biography formats.
    """
    # Try parenthesised range first: "(1920-2005)"
    match = _YEAR_RANGE_RE.search(extract)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Try "(born 1920)" pattern
    match = _BORN_YEAR_RE.search(extract)
    if match:
        return int(match.group(1)), None

    # Try bare "1920-2005" in first sentence
    first_sentence = extract.split(".")[0] if extract else ""
    match = _BIRTH_DEATH_TEXT_RE.search(first_sentence)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Try "born ... 1920" anywhere
    match = _SINGLE_BORN_RE.search(first_sentence)
    if match:
        return int(match.group(1)), None

    return None, None


def _is_person_article(extract: str) -> bool:
    """Heuristic check: does the Wikipedia extract describe a person?

    Looks for birth-related language commonly found in biography articles.
    """
    if not extract:
        return False
    lower = extract[:500].lower()
    person_indicators = [
        "born",
        "was a ",
        "was an ",
        "is a ",
        "is an ",
        "politician",
        "artist",
        "writer",
        "poet",
        "scientist",
        "musician",
        "actor",
        "actress",
        "singer",
        "composer",
        "philosopher",
        "mathematician",
        "physicist",
        "novelist",
        "painter",
        "architect",
        "athlete",
        "footballer",
        "player",
    ]
    return any(indicator in lower for indicator in person_indicators)


async def _fetch_summary(
    client: httpx.AsyncClient,
    title: str,
) -> dict | None:
    """Fetch the Wikipedia REST summary for a given page title.

    Returns the parsed JSON dict on success, or None on failure.
    """
    url = f"{WIKIPEDIA_SUMMARY_URL}/{title}"
    try:
        response = await client.get(url)
        if response.status_code == 200:
            return response.json()
        logger.debug(
            "wikipedia_summary_not_found",
            title=title,
            status=response.status_code,
        )
        return None
    except httpx.HTTPError as exc:
        logger.warning(
            "wikipedia_summary_request_failed",
            title=title,
            error=str(exc),
        )
        return None


async def get_city_description(
    client: httpx.AsyncClient,
    city_name: str,
) -> CityDescription:
    """Fetch a city description from Wikipedia's REST summary endpoint.

    Tries the plain city name first; if that yields a 404, retries with
    the ``{city_name}_(city)`` disambiguation suffix.

    Args:
        client: Shared httpx async client.
        city_name: Name of the city to look up.

    Returns:
        A populated ``CityDescription`` model.

    Raises:
        httpx.HTTPStatusError: If the upstream request fails with an
            unexpected status code after all retries.
        ValueError: If no Wikipedia article could be found for the city.
    """
    log = logger.bind(city_name=city_name)

    # Attempt 1: plain city name
    data = await _fetch_summary(client, city_name)

    # Attempt 2: disambiguation suffix
    if data is None:
        fallback_title = f"{city_name}_(city)"
        log.info("wikipedia_trying_fallback", fallback_title=fallback_title)
        data = await _fetch_summary(client, fallback_title)

    if data is None:
        log.warning("wikipedia_city_not_found")
        raise ValueError(f"Wikipedia article not found for city: {city_name}")

    summary = data.get("extract", "")
    extract_url = (
        data.get("content_urls", {})
        .get("desktop", {})
        .get("page", "")
    )
    thumbnail_url = data.get("thumbnail", {}).get("source")

    log.info(
        "wikipedia_city_description_fetched",
        extract_length=len(summary),
        has_thumbnail=thumbnail_url is not None,
    )

    return CityDescription(
        summary=summary,
        extract_url=extract_url,
        thumbnail_url=thumbnail_url,
    )


async def _fetch_person_summary(
    client: httpx.AsyncClient,
    title: str,
) -> FamousPerson | None:
    """Fetch a Wikipedia summary for a single person page.

    Returns a ``FamousPerson`` if the article looks like a biography,
    otherwise ``None``.
    """
    data = await _fetch_summary(client, title)
    if data is None:
        return None

    extract = data.get("extract", "")
    if not _is_person_article(extract):
        return None

    birth_year, death_year = _parse_years(extract)

    # Build the person's Wikipedia URL
    wikipedia_url = (
        data.get("content_urls", {})
        .get("desktop", {})
        .get("page", f"https://en.wikipedia.org/wiki/{title}")
    )

    # Use the description field if available, fall back to extract
    description = data.get("description") or extract[:200]

    return FamousPerson(
        name=data.get("title", title),
        birth_year=birth_year,
        death_year=death_year,
        description=description,
        wikipedia_url=wikipedia_url,
    )


async def get_famous_people(
    client: httpx.AsyncClient,
    city_name: str,
) -> list[FamousPerson]:
    """Fetch a list of famous people born in a city via Wikipedia.

    Uses the Wikipedia Action API to list category members of
    ``Category:People_from_{city_name}``, then fetches each person's
    summary in parallel to extract biographical details.

    Args:
        client: Shared httpx async client.
        city_name: Name of the city.

    Returns:
        A list of up to 10 ``FamousPerson`` models.
    """
    log = logger.bind(city_name=city_name)

    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:People_from_{city_name}",
        "cmlimit": "20",
        "format": "json",
    }

    try:
        response = await client.get(WIKIPEDIA_ACTION_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        log.warning(
            "wikipedia_category_request_failed",
            error=str(exc),
        )
        return []

    members = data.get("query", {}).get("categorymembers", [])
    if not members:
        log.info("wikipedia_no_category_members")
        return []

    log.info("wikipedia_category_members_found", count=len(members))

    # Fetch summaries in parallel
    tasks = [
        _fetch_person_summary(client, member["title"])
        for member in members
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    people: list[FamousPerson] = []
    for result in results:
        if isinstance(result, Exception):
            log.warning(
                "wikipedia_person_summary_error",
                error=str(result),
            )
            continue
        if result is not None:
            people.append(result)

    # Limit to top 10
    people = people[:10]

    log.info("wikipedia_famous_people_fetched", count=len(people))
    return people
