"""Tests for the GET /city/{city_name}/nearby endpoint."""

import pytest
import respx
from httpx import Response

pytestmark = pytest.mark.asyncio

GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"


def _origin_response(name="Kraków", country="Poland", code="PL", lat="50.06", lng="19.94"):
    return {
        "totalResultsCount": 1,
        "geonames": [
            {
                "geonameId": 1000,
                "name": name,
                "countryName": country,
                "countryCode": code,
                "lat": lat,
                "lng": lng,
                "population": 800000,
                "timezone": {"timeZoneId": "Europe/Warsaw"},
            }
        ],
    }


def _nearby_response(cities):
    """Build a GeoNames response with multiple cities.

    Each entry in `cities` is a dict with keys: geonameId, name, country, code, lat, lng, population.
    """
    geonames = []
    for c in cities:
        geonames.append(
            {
                "geonameId": c["geonameId"],
                "name": c["name"],
                "countryName": c.get("country", "Poland"),
                "countryCode": c.get("code", "PL"),
                "lat": str(c["lat"]),
                "lng": str(c["lng"]),
                "population": c.get("population", 100000),
                "timezone": {"timeZoneId": c.get("tz", "Europe/Warsaw")},
            }
        )
    return {"totalResultsCount": len(geonames), "geonames": geonames}


# Nearby cities ~30-80 km from Kraków
NEARBY_CITIES = [
    {"geonameId": 1000, "name": "Kraków", "lat": 50.06, "lng": 19.94, "population": 800000},
    {"geonameId": 2000, "name": "Katowice", "lat": 50.26, "lng": 19.02, "population": 300000},
    {"geonameId": 3000, "name": "Tarnów", "lat": 50.01, "lng": 20.99, "population": 110000},
    {"geonameId": 4000, "name": "Kielce", "lat": 50.87, "lng": 20.63, "population": 195000},
]


async def test_nearby_happy_path(async_client, respx_mock):
    """Should return nearby cities sorted by distance."""
    responses = iter([
        Response(200, json=_origin_response()),
        Response(200, json=_nearby_response(NEARBY_CITIES)),
    ])
    respx_mock.get(GEONAMES_SEARCH_URL).mock(side_effect=lambda req: next(responses))

    resp = await async_client.get("/city/Kraków/nearby")

    assert resp.status_code == 200
    body = resp.json()
    assert body["origin_city"] == "Kraków"
    assert body["origin_country"] == "Poland"
    assert body["radius_km"] == 100
    assert body["total"] > 0
    # Origin city should be excluded
    city_names = [c["city"] for c in body["nearby_cities"]]
    assert "Kraków" not in city_names
    # Should be sorted by distance
    distances = [c["distance_km"] for c in body["nearby_cities"]]
    assert distances == sorted(distances)
    # Each entry should have coordinates
    for entry in body["nearby_cities"]:
        assert "coordinates" in entry
        assert "latitude" in entry["coordinates"]
        assert "longitude" in entry["coordinates"]
        assert entry["distance_km"] > 0


async def test_nearby_city_not_found(async_client, respx_mock):
    """Should return 404 when the origin city cannot be found."""
    respx_mock.get(GEONAMES_SEARCH_URL).mock(
        return_value=Response(200, json={"totalResultsCount": 0, "geonames": []})
    )

    resp = await async_client.get("/city/Xyzzyville/nearby")

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "CITY_NOT_FOUND"


async def test_nearby_custom_radius(async_client, respx_mock):
    """Should respect the radius_km query parameter."""
    # Kielce is ~100 km away; with radius=50 it should be excluded
    responses = iter([
        Response(200, json=_origin_response()),
        Response(200, json=_nearby_response(NEARBY_CITIES)),
    ])
    respx_mock.get(GEONAMES_SEARCH_URL).mock(side_effect=lambda req: next(responses))

    resp = await async_client.get("/city/Kraków/nearby", params={"radius_km": 50})

    assert resp.status_code == 200
    body = resp.json()
    assert body["radius_km"] == 50
    # All returned cities should be within 50 km
    for entry in body["nearby_cities"]:
        assert entry["distance_km"] <= 50


async def test_nearby_no_cities_in_radius(async_client, respx_mock):
    """Should return empty list when no cities fall within the radius."""
    # Use a very small radius so nothing matches
    responses = iter([
        Response(200, json=_origin_response()),
        # Return only the origin city itself (will be filtered out)
        Response(200, json=_nearby_response([
            {"geonameId": 1000, "name": "Kraków", "lat": 50.06, "lng": 19.94, "population": 800000},
        ])),
    ])
    respx_mock.get(GEONAMES_SEARCH_URL).mock(side_effect=lambda req: next(responses))

    resp = await async_client.get("/city/Kraków/nearby", params={"radius_km": 1})

    assert resp.status_code == 200
    body = resp.json()
    assert body["nearby_cities"] == []
    assert body["total"] == 0
