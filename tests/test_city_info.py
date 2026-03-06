"""Tests for the GET /city/{city_name}/info endpoint."""

import pytest
import respx
from httpx import Response

from app.services.weather_service import _OPENWEATHERMAP_URL
from app.services.wikipedia_service import (
    WIKIPEDIA_ACTION_API_URL,
    WIKIPEDIA_SUMMARY_URL,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# GeoNames mock data
# ---------------------------------------------------------------------------

GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"

GEONAMES_CITY_RESPONSE = {
    "totalResultsCount": 1,
    "geonames": [
        {
            "name": "Kraków",
            "countryName": "Poland",
            "countryCode": "PL",
            "lat": "50.0647",
            "lng": "19.9450",
        }
    ],
}

GEONAMES_EMPTY_RESPONSE = {"totalResultsCount": 0, "geonames": []}

# ---------------------------------------------------------------------------
# Wikipedia mock data
# ---------------------------------------------------------------------------

WIKI_CITY_SUMMARY = {
    "type": "standard",
    "title": "Kraków",
    "extract": "Kraków is the second-largest city in Poland.",
    "content_urls": {
        "desktop": {"page": "https://en.wikipedia.org/wiki/Krak%C3%B3w"}
    },
    "thumbnail": {"source": "https://upload.wikimedia.org/thumb/krakow.jpg"},
}

WIKI_CATEGORY_MEMBERS = {
    "query": {
        "categorymembers": [
            {"title": "Wisława Szymborska", "pageid": 12345},
        ]
    }
}

WIKI_PERSON_SUMMARY = {
    "type": "standard",
    "title": "Wisława Szymborska",
    "extract": "Wisława Szymborska (1923\u20132012) was a Polish poet and Nobel Prize laureate.",
    "description": "Polish poet and Nobel Prize laureate.",
    "content_urls": {
        "desktop": {
            "page": "https://en.wikipedia.org/wiki/Wis%C5%82awa_Szymborska"
        }
    },
}

# ---------------------------------------------------------------------------
# Weather mock data
# ---------------------------------------------------------------------------

WEATHER_RESPONSE = {
    "main": {
        "temp": 12.4,
        "feels_like": 10.1,
        "humidity": 68,
        "pressure": 1012,
    },
    "weather": [{"description": "partly cloudy", "icon": "02d"}],
    "wind": {"speed": 4.25, "deg": 315},
    "visibility": 10000,
    "sys": {"sunrise": 1709708400, "sunset": 1709750400},
    "timezone": 3600,
}


# ---------------------------------------------------------------------------
# Helper to set up all mocks for the happy-path scenario
# ---------------------------------------------------------------------------

def _mock_all_apis(respx_mock):
    """Set up respx mocks for GeoNames, Wikipedia, and OpenWeatherMap."""
    # GeoNames city lookup
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(200, json=GEONAMES_CITY_RESPONSE)
    )

    # Wikipedia city summary (match any path under the summary URL)
    respx_mock.get(url__startswith=WIKIPEDIA_SUMMARY_URL).mock(
        return_value=Response(200, json=WIKI_CITY_SUMMARY)
    )

    # Wikipedia category members (famous people)
    respx_mock.get(WIKIPEDIA_ACTION_API_URL).mock(
        return_value=Response(200, json=WIKI_CATEGORY_MEMBERS)
    )

    # OpenWeatherMap
    respx_mock.get(_OPENWEATHERMAP_URL).mock(
        return_value=Response(200, json=WEATHER_RESPONSE)
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_get_city_info_happy_path(async_client, respx_mock):
    """Happy path: all upstream APIs return data, response is complete."""
    _mock_all_apis(respx_mock)

    resp = await async_client.get("/city/Kraków/info")

    assert resp.status_code == 200
    body = resp.json()

    assert body["city"] == "Kraków"
    assert body["country"] == "Poland"
    assert body["country_code"] == "PL"
    assert body["coordinates"]["latitude"] == 50.0647

    # Description
    assert body["description"] is not None
    assert "second-largest" in body["description"]["summary"]

    # Weather
    assert body["weather"] is not None
    assert body["weather"]["temperature_celsius"] == 12.4

    # Data sources
    assert body["data_sources"]["weather"] == "OpenWeatherMap"

    # No warnings on happy path
    assert body["warnings"] == []


async def test_get_city_info_wikipedia_not_found(async_client, respx_mock):
    """When Wikipedia has no article, the response degrades gracefully with a warning."""
    # GeoNames succeeds
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(200, json=GEONAMES_CITY_RESPONSE)
    )

    # Wikipedia city summary -- 404 for both attempts (plain + fallback)
    respx_mock.get(url__startswith=WIKIPEDIA_SUMMARY_URL).mock(
        return_value=Response(404, json={"type": "not_found"})
    )

    # Wikipedia category members -- empty
    respx_mock.get(WIKIPEDIA_ACTION_API_URL).mock(
        return_value=Response(200, json={"query": {"categorymembers": []}})
    )

    # Weather succeeds
    respx_mock.get(_OPENWEATHERMAP_URL).mock(
        return_value=Response(200, json=WEATHER_RESPONSE)
    )

    resp = await async_client.get("/city/Kraków/info")

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] is None
    assert body["weather"] is not None
    assert any("description" in w.lower() or "unavailable" in w.lower() for w in body["warnings"])


async def test_get_city_info_weather_failure(async_client, respx_mock):
    """When the weather API fails, partial response is returned with a warning."""
    # GeoNames succeeds
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(200, json=GEONAMES_CITY_RESPONSE)
    )

    # Wikipedia succeeds (match any path under the summary URL)
    respx_mock.get(url__startswith=WIKIPEDIA_SUMMARY_URL).mock(
        return_value=Response(200, json=WIKI_CITY_SUMMARY)
    )
    respx_mock.get(WIKIPEDIA_ACTION_API_URL).mock(
        return_value=Response(200, json=WIKI_CATEGORY_MEMBERS)
    )

    # Weather fails
    respx_mock.get(_OPENWEATHERMAP_URL).mock(
        return_value=Response(500, text="Internal Server Error")
    )

    resp = await async_client.get("/city/Kraków/info")

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] is not None
    assert body["weather"] is None
    assert any("weather" in w.lower() for w in body["warnings"])


async def test_get_city_info_city_not_found_returns_404(async_client, respx_mock):
    """When GeoNames returns no results, the endpoint returns 404."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(200, json=GEONAMES_EMPTY_RESPONSE)
    )

    resp = await async_client.get("/city/Xyzzyville/info")

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "CITY_NOT_FOUND"


async def test_get_city_info_with_country_code(async_client, respx_mock):
    """Providing country_code disambiguates the city lookup."""
    _mock_all_apis(respx_mock)

    resp = await async_client.get(
        "/city/Kraków/info", params={"country_code": "PL"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["country_code"] == "PL"
    assert body["city"] == "Kraków"
