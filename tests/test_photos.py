"""Tests for the GET /city/{city_name}/photos endpoint."""

import pytest
import respx
from httpx import Response

from app.services.photos_service import COMMONS_API_URL

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

GEONAMES_SEARCH_URL = "http://api.geonames.org/searchJSON"

COMMONS_CATEGORY_RESPONSE = {
    "query": {
        "categorymembers": [
            {"title": "File:Krakow panorama.jpg", "pageid": 1001},
            {"title": "File:Wawel Castle.jpg", "pageid": 1002},
        ]
    }
}

COMMONS_IMAGEINFO_RESPONSE = {
    "query": {
        "pages": {
            "1001": {
                "title": "File:Krakow panorama.jpg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/krakow_panorama.jpg",
                        "thumburl": "https://upload.wikimedia.org/krakow_panorama_thumb.jpg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Krakow_panorama.jpg",
                        "mime": "image/jpeg",
                        "extmetadata": {
                            "ImageDescription": {
                                "value": "A panoramic view of the old town square."
                            }
                        },
                    }
                ],
            },
            "1002": {
                "title": "File:Wawel Castle.jpg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/wawel_castle.jpg",
                        "thumburl": "https://upload.wikimedia.org/wawel_castle_thumb.jpg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Wawel_Castle.jpg",
                        "mime": "image/jpeg",
                        "extmetadata": {
                            "ImageDescription": {
                                "value": "The castle on Wawel hill."
                            }
                        },
                    }
                ],
            },
        }
    }
}

COMMONS_EMPTY_CATEGORY = {"query": {"categorymembers": []}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_photos_happy_path(async_client, respx_mock):
    """Happy path: photos are returned from Wikimedia Commons."""
    # First call: category members, second call: imageinfo
    respx_mock.get(COMMONS_API_URL).mock(
        side_effect=[
            Response(200, json=COMMONS_CATEGORY_RESPONSE),
            Response(200, json=COMMONS_IMAGEINFO_RESPONSE),
        ]
    )

    resp = await async_client.get("/city/Krak%C3%B3w/photos")

    assert resp.status_code == 200
    body = resp.json()
    assert body["city"] == "Krak\u00f3w"
    assert len(body["photos"]) == 2
    assert body["photos"][0]["title"] == "Krakow panorama.jpg"
    assert body["photos"][0]["thumbnail_url"] is not None


async def test_photos_empty(async_client, respx_mock):
    """When no photos are found, return empty list."""
    respx_mock.get(COMMONS_API_URL).mock(
        return_value=Response(200, json=COMMONS_EMPTY_CATEGORY)
    )

    resp = await async_client.get("/city/Xyzzyville/photos")

    assert resp.status_code == 200
    body = resp.json()
    assert body["photos"] == []
    assert body["total"] == 0


async def test_photos_category_filter(async_client, respx_mock):
    """Category filter returns only matching photos."""
    respx_mock.get(COMMONS_API_URL).mock(
        side_effect=[
            Response(200, json=COMMONS_CATEGORY_RESPONSE),
            Response(200, json=COMMONS_IMAGEINFO_RESPONSE),
        ]
    )

    resp = await async_client.get("/city/Krak%C3%B3w/photos?category=architecture")

    assert resp.status_code == 200
    body = resp.json()
    # "Wawel Castle" contains "castle" -> architecture
    for photo in body["photos"]:
        assert photo["category"] == "architecture"
