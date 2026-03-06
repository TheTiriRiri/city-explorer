"""Tests for the GET /countries endpoint."""

import httpx
import pytest
import respx
from httpx import Response

from app.services.countries_service import RESTCOUNTRIES_URL

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Sample upstream data (RestCountries v3.1 format)
# ---------------------------------------------------------------------------

SAMPLE_COUNTRIES_RAW = [
    {
        "name": {"common": "Poland"},
        "cca2": "PL",
        "capital": ["Warsaw"],
        "region": "Europe",
        "flags": {"svg": "https://flagcdn.com/pl.svg", "png": "https://flagcdn.com/w320/pl.png"},
    },
    {
        "name": {"common": "Germany"},
        "cca2": "DE",
        "capital": ["Berlin"],
        "region": "Europe",
        "flags": {"svg": "https://flagcdn.com/de.svg", "png": "https://flagcdn.com/w320/de.png"},
    },
    {
        "name": {"common": "United States"},
        "cca2": "US",
        "capital": ["Washington, D.C."],
        "region": "Americas",
        "flags": {"svg": "https://flagcdn.com/us.svg", "png": "https://flagcdn.com/w320/us.png"},
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_get_countries_returns_list(async_client, respx_mock):
    """Happy path: endpoint returns a sorted list of countries."""
    respx_mock.get(RESTCOUNTRIES_URL).mock(
        return_value=Response(200, json=SAMPLE_COUNTRIES_RAW)
    )

    resp = await async_client.get("/countries")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    # Countries should be sorted alphabetically by name
    names = [c["name"] for c in body["countries"]]
    assert names == ["Germany", "Poland", "United States"]


async def test_get_countries_search_filter(async_client, respx_mock):
    """Search parameter filters countries by case-insensitive partial match."""
    respx_mock.get(RESTCOUNTRIES_URL).mock(
        return_value=Response(200, json=SAMPLE_COUNTRIES_RAW)
    )

    resp = await async_client.get("/countries", params={"search": "pol"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["countries"][0]["name"] == "Poland"


async def test_get_countries_empty_search_returns_all(async_client, respx_mock):
    """An empty search string should return all countries (no filter applied)."""
    respx_mock.get(RESTCOUNTRIES_URL).mock(
        return_value=Response(200, json=SAMPLE_COUNTRIES_RAW)
    )

    resp = await async_client.get("/countries", params={"search": ""})

    assert resp.status_code == 200
    body = resp.json()
    # Empty string is falsy, so no filtering should happen
    assert body["count"] == 3


async def test_get_countries_upstream_error_returns_503(async_client, respx_mock):
    """When the RestCountries API is unreachable, the endpoint returns 503."""
    respx_mock.get(RESTCOUNTRIES_URL).mock(
        return_value=Response(500, json={"error": "Internal Server Error"})
    )

    resp = await async_client.get("/countries")

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "UPSTREAM_ERROR"
