"""Tests for the GET /city/{city_name}/timeline endpoint."""

import pytest
import respx
from httpx import Response

from app.services.timeline_service import WIKIPEDIA_API_URL

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

WIKI_SECTIONS_RESPONSE = {
    "parse": {
        "title": "Krak\u00f3w",
        "sections": [
            {"index": "1", "line": "Etymology"},
            {"index": "2", "line": "History"},
            {"index": "3", "line": "Geography"},
        ],
    }
}

WIKI_SECTIONS_NO_HISTORY = {
    "parse": {
        "title": "Xyzzyville",
        "sections": [
            {"index": "1", "line": "Geography"},
            {"index": "2", "line": "Demographics"},
        ],
    }
}

WIKI_HISTORY_WIKITEXT = {
    "parse": {
        "title": "Krak\u00f3w",
        "wikitext": {
            "*": """== History ==
* [[1257]] \u2013 The city received its [[city rights|municipal charter]].
* 1364 \u2013 [[Jagiellonian University]] was founded by [[Casimir III]].
* 1596 \u2013 The capital was moved to [[Warsaw]].
"""
        },
    }
}

WIKI_EMPTY_WIKITEXT = {
    "parse": {
        "title": "Test",
        "wikitext": {"*": "== History ==\nNo specific events documented."},
    }
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_timeline_happy_path(async_client, respx_mock):
    """Happy path: timeline events are parsed from Wikipedia History section."""
    respx_mock.get(WIKIPEDIA_API_URL).mock(
        side_effect=[
            Response(200, json=WIKI_SECTIONS_RESPONSE),
            Response(200, json=WIKI_HISTORY_WIKITEXT),
        ]
    )

    resp = await async_client.get("/city/Krak%C3%B3w/timeline")

    assert resp.status_code == 200
    body = resp.json()
    assert body["city"] == "Krak\u00f3w"
    assert len(body["events"]) == 3
    assert body["events"][0]["year"] == 1257
    assert "municipal charter" in body["events"][0]["event"]
    assert body["events"][1]["year"] == 1364
    assert body["events"][2]["year"] == 1596


async def test_timeline_no_history_section(async_client, respx_mock):
    """When there's no History section, return empty events."""
    # First call: sections (no History), second: fallback sections (also no History)
    respx_mock.get(WIKIPEDIA_API_URL).mock(
        return_value=Response(200, json=WIKI_SECTIONS_NO_HISTORY)
    )

    resp = await async_client.get("/city/Xyzzyville/timeline")

    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []
    assert body["total"] == 0


async def test_timeline_wikitext_parsing(async_client, respx_mock):
    """Wikitext markup is cleaned from events."""
    respx_mock.get(WIKIPEDIA_API_URL).mock(
        side_effect=[
            Response(200, json=WIKI_SECTIONS_RESPONSE),
            Response(200, json=WIKI_HISTORY_WIKITEXT),
        ]
    )

    resp = await async_client.get("/city/Krak%C3%B3w/timeline")

    body = resp.json()
    # Wikilinks should be stripped: [[Jagiellonian University]] -> Jagiellonian University
    event_1364 = next(e for e in body["events"] if e["year"] == 1364)
    assert "[[" not in event_1364["event"]
    assert "Jagiellonian University" in event_1364["event"]
