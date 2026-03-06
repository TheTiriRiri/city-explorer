"""Tests for the GET /countries/{country_code}/cities endpoint."""

import httpx
import pytest
import respx
from httpx import Response

from app.services.cities_service import GEONAMES_URL

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Sample upstream data (GeoNames searchJSON format)
# ---------------------------------------------------------------------------

SAMPLE_GEONAMES_RESPONSE = {
    "totalResultsCount": 3,
    "geonames": [
        {
            "name": "Warsaw",
            "lat": "52.2298",
            "lng": "21.0118",
            "population": 1860281,
            "timezone": {"timeZoneId": "Europe/Warsaw"},
        },
        {
            "name": "Kraków",
            "lat": "50.0647",
            "lng": "19.9450",
            "population": 779966,
            "timezone": {"timeZoneId": "Europe/Warsaw"},
        },
        {
            "name": "Łódź",
            "lat": "51.7592",
            "lng": "19.4560",
            "population": 672185,
            "timezone": {"timeZoneId": "Europe/Warsaw"},
        },
    ],
}

# RestCountries response used by _resolve_country_name
COUNTRY_NAME_RESPONSE = {"name": {"common": "Poland"}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_get_cities_valid_country(async_client, respx_mock):
    """Happy path: valid country code returns a list of cities."""
    respx_mock.get(GEONAMES_URL).mock(
        return_value=Response(200, json=SAMPLE_GEONAMES_RESPONSE)
    )
    respx_mock.get(url__startswith="https://restcountries.com/v3.1/alpha/").mock(
        return_value=Response(200, json=COUNTRY_NAME_RESPONSE)
    )

    resp = await async_client.get("/countries/PL/cities")

    assert resp.status_code == 200
    body = resp.json()
    assert body["country_code"] == "PL"
    assert body["total"] == 3
    assert len(body["cities"]) == 3
    assert body["cities"][0]["name"] == "Warsaw"


async def test_get_cities_invalid_country_returns_404(async_client, respx_mock):
    """An invalid country code yields a 404 with COUNTRY_NOT_FOUND error."""
    respx_mock.get(GEONAMES_URL).mock(
        return_value=Response(200, json={"totalResultsCount": 0, "geonames": []})
    )

    resp = await async_client.get("/countries/ZZ/cities")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "COUNTRY_NOT_FOUND"


async def test_get_cities_pagination(async_client, respx_mock):
    """Pagination parameters (page, per_page) slice results correctly."""
    respx_mock.get(GEONAMES_URL).mock(
        return_value=Response(200, json=SAMPLE_GEONAMES_RESPONSE)
    )
    respx_mock.get(url__startswith="https://restcountries.com/v3.1/alpha/").mock(
        return_value=Response(200, json=COUNTRY_NAME_RESPONSE)
    )

    resp = await async_client.get(
        "/countries/PL/cities", params={"page": 2, "per_page": 2}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 2
    assert body["per_page"] == 2
    # Page 2 with per_page=2 should return only the 3rd item
    assert len(body["cities"]) == 1
    assert body["cities"][0]["name"] == "Łódź"


async def test_get_cities_search_filter(async_client, respx_mock):
    """Search parameter filters cities by case-insensitive partial match."""
    respx_mock.get(GEONAMES_URL).mock(
        return_value=Response(200, json=SAMPLE_GEONAMES_RESPONSE)
    )
    respx_mock.get(url__startswith="https://restcountries.com/v3.1/alpha/").mock(
        return_value=Response(200, json=COUNTRY_NAME_RESPONSE)
    )

    resp = await async_client.get(
        "/countries/PL/cities", params={"search": "krak"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["cities"][0]["name"] == "Kraków"


async def test_get_cities_upstream_error_returns_503(async_client, respx_mock):
    """When GeoNames is unreachable, the endpoint returns 503."""
    respx_mock.get(GEONAMES_URL).mock(
        return_value=Response(500, text="Internal Server Error")
    )

    resp = await async_client.get("/countries/PL/cities")

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "UPSTREAM_ERROR"
