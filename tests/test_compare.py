"""Tests for the GET /cities/compare endpoint."""

import pytest
import respx
from httpx import Response

from app.services.weather_service import _OPENWEATHERMAP_URL
from app.services.wikipedia_service import WIKIPEDIA_ACTION_API_URL

pytestmark = pytest.mark.asyncio

GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"


def _geonames_response(name, country, code, population=500000, tz="Europe/Warsaw"):
    return {
        "totalResultsCount": 1,
        "geonames": [
            {
                "name": name,
                "countryName": country,
                "countryCode": code,
                "lat": "50.0",
                "lng": "20.0",
                "population": population,
                "timezone": {"timeZoneId": tz},
            }
        ],
    }


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

WIKI_CATEGORY_EMPTY = {"query": {"categorymembers": []}}


def _mock_apis_for_cities(respx_mock, city_names):
    """Set up mocks that respond for any city."""
    # GeoNames — use side_effect to return different data per city
    geonames_responses = iter(
        [_geonames_response(name, "Poland", "PL") for name in city_names]
    )
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        side_effect=lambda req: Response(200, json=next(geonames_responses))
    )

    # Weather
    respx_mock.get(_OPENWEATHERMAP_URL).mock(
        return_value=Response(200, json=WEATHER_RESPONSE)
    )

    # Wikipedia famous people
    respx_mock.get(WIKIPEDIA_ACTION_API_URL).mock(
        return_value=Response(200, json=WIKI_CATEGORY_EMPTY)
    )


async def test_compare_happy_path(async_client, respx_mock):
    """Two cities compared successfully."""
    _mock_apis_for_cities(respx_mock, ["Kraków", "Warszawa"])

    resp = await async_client.get("/cities/compare", params={"cities": "Kraków,Warszawa"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cities"]) == 2
    assert body["cities"][0]["city"] == "Kraków"
    assert body["cities"][1]["city"] == "Warszawa"
    assert body["cities"][0]["population"] == 500000
    assert body["cities"][0]["timezone"] == "Europe/Warsaw"
    assert body["cities"][0]["weather"] is not None
    assert body["data_sources"]["weather"] == "OpenWeatherMap"


async def test_compare_too_few_cities(async_client):
    """Should return 400 when fewer than 2 cities provided."""
    resp = await async_client.get("/cities/compare", params={"cities": "Kraków"})

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "TOO_FEW_CITIES"


async def test_compare_too_many_cities(async_client):
    """Should return 400 when more than 5 cities provided."""
    cities = ",".join(["City"] * 6)
    resp = await async_client.get("/cities/compare", params={"cities": cities})

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "TOO_MANY_CITIES"


async def test_compare_no_cities_found(async_client, respx_mock):
    """Should return 404 when none of the cities can be resolved."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(200, json={"totalResultsCount": 0, "geonames": []})
    )

    resp = await async_client.get("/cities/compare", params={"cities": "Xyzzy,Plugh"})

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "NO_CITIES_FOUND"


async def test_compare_partial_city_failure(async_client, respx_mock):
    """When one city can't be resolved, the other is still returned."""
    responses = iter([
        Response(200, json=_geonames_response("Kraków", "Poland", "PL")),
        Response(200, json={"totalResultsCount": 0, "geonames": []}),
    ])
    respx_mock.get(GEONAMES_SEARCH_URL).mock(side_effect=lambda req: next(responses))
    respx_mock.get(_OPENWEATHERMAP_URL).mock(
        return_value=Response(200, json=WEATHER_RESPONSE)
    )
    respx_mock.get(WIKIPEDIA_ACTION_API_URL).mock(
        return_value=Response(200, json=WIKI_CATEGORY_EMPTY)
    )

    resp = await async_client.get("/cities/compare", params={"cities": "Kraków,Xyzzy"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cities"]) == 1
    assert body["cities"][0]["city"] == "Kraków"


async def test_compare_weather_failure_degrades_gracefully(async_client, respx_mock):
    """When weather API fails, city still appears with weather=None and a warning."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(200, json=_geonames_response("Kraków", "Poland", "PL"))
    )
    respx_mock.get(_OPENWEATHERMAP_URL).mock(
        return_value=Response(500, text="Internal Server Error")
    )
    respx_mock.get(WIKIPEDIA_ACTION_API_URL).mock(
        return_value=Response(200, json=WIKI_CATEGORY_EMPTY)
    )

    resp = await async_client.get("/cities/compare", params={"cities": "Kraków,Kraków"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cities"]) == 2
    assert body["cities"][0]["weather"] is None
    assert any("weather" in w.lower() for w in body["cities"][0]["warnings"])


async def test_compare_missing_query_param(async_client):
    """Should return 422 when cities param is missing."""
    resp = await async_client.get("/cities/compare")
    assert resp.status_code == 422
