"""Service for fetching city data from the GeoNames API."""

import httpx
import structlog

from app.models.city import City

logger = structlog.get_logger(__name__)

GEONAMES_URL = "http://api.geonames.org/searchJSON"


async def fetch_cities_for_country(
    country_code: str,
    client: httpx.AsyncClient,
    geonames_username: str,
) -> list[City]:
    """Fetch cities for a country from the GeoNames API.

    Args:
        country_code: ISO 3166-1 alpha-2 country code (e.g. "PL", "US").
        client: Shared httpx.AsyncClient instance.
        geonames_username: GeoNames API username from settings.

    Returns:
        A list of City models sorted by population descending.

    Raises:
        httpx.HTTPStatusError: If the API returns a non-2xx response.
        httpx.RequestError: If a network-level error occurs.
        ValueError: If the country code yields no results or is invalid.
    """
    logger.info(
        "cities_fetch_start",
        country_code=country_code,
    )

    try:
        response = await client.get(
            GEONAMES_URL,
            params={
                "country": country_code,
                "featureClass": "P",
                "maxRows": 1000,
                "username": geonames_username,
                "orderby": "population",
            },
        )
        response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.error(
            "cities_fetch_http_error",
            status_code=response.status_code,
            url=str(response.url),
            country_code=country_code,
        )
        raise
    except httpx.RequestError as exc:
        logger.error(
            "cities_fetch_request_error",
            url=str(exc.request.url),
            country_code=country_code,
            exc_info=True,
        )
        raise

    data = response.json()

    # GeoNames returns an error status inside the JSON body for invalid
    # requests (e.g. bad username) rather than using HTTP status codes.
    if "status" in data:
        error_message = data["status"].get("message", "Unknown GeoNames error")
        error_value = data["status"].get("value")
        logger.error(
            "cities_fetch_api_error",
            country_code=country_code,
            geonames_error=error_message,
            geonames_error_code=error_value,
        )
        raise ValueError(f"GeoNames API error: {error_message}")

    geonames = data.get("geonames", [])

    if not geonames:
        logger.warning(
            "cities_fetch_empty",
            country_code=country_code,
        )
        raise ValueError(
            f"No cities found for country code '{country_code}'. "
            "The country code may be invalid."
        )

    cities = [_parse_city(item) for item in geonames]

    logger.info(
        "cities_fetch_complete",
        country_code=country_code,
        count=len(cities),
    )
    return cities


def _parse_city(data: dict) -> City:
    """Map a single raw GeoNames JSON object to a City model.

    Handles missing or null fields gracefully.
    """
    name = data.get("name", "Unknown")
    latitude = float(data.get("lat", 0.0))
    longitude = float(data.get("lng", 0.0))

    raw_population = data.get("population")
    population = int(raw_population) if raw_population is not None else None

    timezone_info = data.get("timezone")
    timezone = (
        timezone_info.get("timeZoneId")
        if isinstance(timezone_info, dict)
        else None
    )

    return City(
        name=name,
        latitude=latitude,
        longitude=longitude,
        population=population,
        timezone=timezone,
    )
