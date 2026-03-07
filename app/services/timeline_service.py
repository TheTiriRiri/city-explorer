"""Wikipedia timeline service for city historical events."""

import re

import httpx
import structlog

from app.models.timeline import HistoricalEvent

logger = structlog.get_logger(__name__)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

# Regex to find year-event patterns in wikitext
_YEAR_EVENT_RE = re.compile(
    r"(?:^|\n)\s*\*?\s*(?:\[?\[?)(\d{3,4})(?:\]?\]?)\s*[-\u2013:]\s*(.+?)(?=\n|$)"
)

# Patterns to clean wikitext markup
_WIKILINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
_TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/?>", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BOLD_ITALIC_RE = re.compile(r"'{2,5}")


def _clean_wikitext(text: str) -> str:
    """Remove wikitext markup, refs, templates, and HTML tags."""
    text = _REF_RE.sub("", text)
    text = _TEMPLATE_RE.sub("", text)
    text = _WIKILINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _BOLD_ITALIC_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_events(wikitext: str) -> list[HistoricalEvent]:
    """Extract year-event pairs from wikitext of a History section."""
    events: list[HistoricalEvent] = []
    seen_years: set[tuple[int, str]] = set()

    for match in _YEAR_EVENT_RE.finditer(wikitext):
        year_str = match.group(1)
        event_text = match.group(2).strip()

        year = int(year_str)
        if year < 100 or year > 2100:
            continue

        event_text = _clean_wikitext(event_text)
        if not event_text or len(event_text) < 5:
            continue

        # Truncate long events
        if len(event_text) > 500:
            event_text = event_text[:497] + "..."

        key = (year, event_text[:50])
        if key in seen_years:
            continue
        seen_years.add(key)

        events.append(HistoricalEvent(year=year, event=event_text))

    events.sort(key=lambda e: e.year)
    return events[:50]


async def _find_history_section(
    client: httpx.AsyncClient,
    page_title: str,
) -> int | None:
    """Find the index of the 'History' section in a Wikipedia article."""
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "sections",
        "format": "json",
    }
    try:
        response = await client.get(WIKIPEDIA_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("wikipedia_sections_request_failed", page=page_title, error=str(exc))
        return None

    if "error" in data:
        return None

    sections = data.get("parse", {}).get("sections", [])
    for section in sections:
        if section.get("line", "").lower() == "history":
            return int(section["index"])
    return None


async def _fetch_section_wikitext(
    client: httpx.AsyncClient,
    page_title: str,
    section_index: int,
) -> str | None:
    """Fetch the wikitext of a specific section."""
    params = {
        "action": "parse",
        "page": page_title,
        "section": str(section_index),
        "prop": "wikitext",
        "format": "json",
    }
    try:
        response = await client.get(WIKIPEDIA_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("wikipedia_wikitext_request_failed", page=page_title, error=str(exc))
        return None

    if "error" in data:
        return None

    return data.get("parse", {}).get("wikitext", {}).get("*")


async def get_city_timeline(
    client: httpx.AsyncClient,
    city_name: str,
) -> list[HistoricalEvent]:
    """Fetch historical timeline events for a city from Wikipedia.

    Finds the History section, downloads its wikitext, and parses year-event pairs.
    """
    log = logger.bind(city_name=city_name)

    # Try plain city name first
    section_idx = await _find_history_section(client, city_name)
    page_title = city_name

    # Fallback: try {city}_(city)
    if section_idx is None:
        fallback_title = f"{city_name}_(city)"
        log.info("timeline_trying_fallback", fallback_title=fallback_title)
        section_idx = await _find_history_section(client, fallback_title)
        if section_idx is not None:
            page_title = fallback_title

    if section_idx is None:
        log.info("timeline_no_history_section")
        return []

    wikitext = await _fetch_section_wikitext(client, page_title, section_idx)
    if not wikitext:
        log.info("timeline_empty_wikitext")
        return []

    events = _parse_events(wikitext)
    log.info("timeline_events_parsed", count=len(events))
    return events
