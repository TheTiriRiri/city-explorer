"""Tests for the GET /city/random endpoint."""

import pytest
import respx
from httpx import Response

pytestmark = pytest.mark.asyncio

GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"


def _geonames_search_response(cities):
    """Build a GeoNames searchJSON response with the given city dicts."""
    return {
        "totalResultsCount": len(cities),
        "geonames": cities,
    }


def _city_entry(name="Berlin", country="Germany", code="DE", population=3700000,
                lat="52.52", lng="13.405", tz="Europe/Berlin"):
    return {
        "name": name,
        "countryName": country,
        "countryCode": code,
        "lat": lat,
        "lng": lng,
        "population": population,
        "timezone": {"timeZoneId": tz},
    }


async def test_random_city_happy_path(async_client, respx_mock):
    """Should return a random city with all expected fields."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(
            200,
            json=_geonames_search_response([
                _city_entry("Berlin", "Germany", "DE", 3700000),
                _city_entry("Munich", "Germany", "DE", 1500000),
            ]),
        )
    )

    resp = await async_client.get("/city/random")

    assert resp.status_code == 200
    body = resp.json()
    assert body["city"] in ("Berlin", "Munich")
    assert body["country"] in ("Germany",)
    assert body["country_code"] == "DE"
    assert "latitude" in body["coordinates"]
    assert "longitude" in body["coordinates"]
    assert body["population"] is not None
    assert body["timezone"] is not None
    assert body["data_sources"]["geography"] == "GeoNames"


async def test_random_city_with_region_filter(async_client, respx_mock):
    """Should pass continentCode to GeoNames when region is specified."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(
            200,
            json=_geonames_search_response([
                _city_entry("Tokyo", "Japan", "JP", 14000000, tz="Asia/Tokyo"),
            ]),
        )
    )

    resp = await async_client.get("/city/random", params={"region": "Asia"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["city"] == "Tokyo"

    # Verify the request had continentCode=AS
    geonames_call = respx_mock.calls[0]
    assert geonames_call.request.url.params["continentCode"] == "AS"


async def test_random_city_with_population_filters(async_client, respx_mock):
    """Should filter cities by min/max population."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(
            200,
            json=_geonames_search_response([
                _city_entry("BigCity", "X", "XX", 5000000),
                _city_entry("MedCity", "X", "XX", 500000),
                _city_entry("SmallCity", "X", "XX", 50000),
            ]),
        )
    )

    resp = await async_client.get(
        "/city/random",
        params={"min_population": 100000, "max_population": 1000000},
    )

    assert resp.status_code == 200
    body = resp.json()
    # Only MedCity matches the range
    assert body["city"] == "MedCity"
    assert body["population"] == 500000


async def test_random_city_no_results_returns_404(async_client, respx_mock):
    """Should return 404 when no cities match the criteria."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(
            200,
            json=_geonames_search_response([]),
        )
    )

    resp = await async_client.get(
        "/city/random",
        params={"region": "Europe", "min_population": 100000},
    )

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "NO_CITIES_FOUND"


async def test_random_city_invalid_region_returns_400(async_client):
    """Should return 400 for an unrecognized region name."""
    resp = await async_client.get("/city/random", params={"region": "Atlantis"})

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "INVALID_REGION"
