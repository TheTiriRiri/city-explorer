"""Tests for the GET /city/{city_name}/pois endpoint."""

import pytest
import respx
from httpx import Response

from app.services.poi_service import OVERPASS_API_URL

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

OVERPASS_RESPONSE = {
    "elements": [
        {
            "type": "node",
            "id": 100,
            "lat": 50.0614,
            "lon": 19.9372,
            "tags": {"name": "Wawel Castle", "historic": "castle"},
        },
        {
            "type": "node",
            "id": 101,
            "lat": 50.0617,
            "lon": 19.9352,
            "tags": {"name": "National Museum", "tourism": "museum"},
        },
        {
            "type": "node",
            "id": 102,
            "lat": 50.0620,
            "lon": 19.9400,
            "tags": {"tourism": "attraction"},  # No name -> should be filtered
        },
        {
            "type": "node",
            "id": 103,
            "lat": 50.0630,
            "lon": 19.9410,
            "tags": {"name": "Planty Park", "leisure": "park"},
        },
    ]
}

OVERPASS_EMPTY = {"elements": []}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_pois_happy_path(async_client, respx_mock):
    """Happy path: POIs are returned from Overpass API."""
    respx_mock.post(OVERPASS_API_URL).mock(
        return_value=Response(200, json=OVERPASS_RESPONSE)
    )

    resp = await async_client.get(
        "/city/Krak%C3%B3w/pois",
        params={"lat": 50.0647, "lon": 19.9450},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["city"] == "Krak\u00f3w"
    # 3 POIs (unnamed one filtered out)
    assert len(body["pois"]) == 3
    names = [p["name"] for p in body["pois"]]
    assert "Wawel Castle" in names
    assert "National Museum" in names
    assert "Planty Park" in names


async def test_pois_empty(async_client, respx_mock):
    """When Overpass returns no elements, return empty list."""
    respx_mock.post(OVERPASS_API_URL).mock(
        return_value=Response(200, json=OVERPASS_EMPTY)
    )

    resp = await async_client.get(
        "/city/Xyzzyville/pois",
        params={"lat": 0.0, "lon": 0.0},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["pois"] == []
    assert body["total"] == 0


async def test_pois_category_filter(async_client, respx_mock):
    """Category filter returns only matching POIs."""
    respx_mock.post(OVERPASS_API_URL).mock(
        return_value=Response(200, json=OVERPASS_RESPONSE)
    )

    resp = await async_client.get(
        "/city/Krak%C3%B3w/pois",
        params={"lat": 50.0647, "lon": 19.9450, "category": "monument"},
    )

    assert resp.status_code == 200
    body = resp.json()
    # Only castle -> monument category
    for poi in body["pois"]:
        assert poi["category"] == "monument"


async def test_pois_unnamed_filtered(async_client, respx_mock):
    """Elements without a name tag are excluded from results."""
    respx_mock.post(OVERPASS_API_URL).mock(
        return_value=Response(200, json=OVERPASS_RESPONSE)
    )

    resp = await async_client.get(
        "/city/Krak%C3%B3w/pois",
        params={"lat": 50.0647, "lon": 19.9450},
    )

    body = resp.json()
    # Element with id=102 has no name and should be excluded
    osm_ids = [p.get("osm_id") for p in body["pois"]]
    assert 102 not in osm_ids
