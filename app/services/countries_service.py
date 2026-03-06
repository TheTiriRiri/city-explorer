"""Service for fetching country data from the RestCountries API."""

import httpx
import structlog

from app.models.country import Country

logger = structlog.get_logger(__name__)

RESTCOUNTRIES_URL = "https://restcountries.com/v3.1/all"
RESTCOUNTRIES_FIELDS = "name,cca2,capital,region,flags"


async def fetch_all_countries(client: httpx.AsyncClient) -> list[Country]:
    """Fetch all countries from the RestCountries API.

    Args:
        client: Shared httpx.AsyncClient instance.

    Returns:
        A list of Country models sorted alphabetically by name.

    Raises:
        httpx.HTTPStatusError: If the API returns a non-2xx response.
        httpx.RequestError: If a network-level error occurs.
    """
    logger.info("countries_fetch_start")

    try:
        response = await client.get(
            RESTCOUNTRIES_URL,
            params={"fields": RESTCOUNTRIES_FIELDS},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.error(
            "countries_fetch_http_error",
            status_code=response.status_code,
            url=str(response.url),
        )
        raise
    except httpx.RequestError as exc:
        logger.error(
            "countries_fetch_request_error",
            url=str(exc.request.url),
            exc_info=True,
        )
        raise

    raw_countries: list[dict] = response.json()
    countries = [_parse_country(item) for item in raw_countries]
    countries.sort(key=lambda c: c.name)

    logger.info("countries_fetch_complete", count=len(countries))
    return countries


def _parse_country(data: dict) -> Country:
    """Map a single raw RestCountries JSON object to a Country model.

    Handles edge cases such as missing capital or flags.
    """
    name = data.get("name", {}).get("common", "Unknown")
    code = data.get("cca2", "")

    # Some territories have an empty capital list or no capital at all.
    capitals = data.get("capital")
    capital = capitals[0] if capitals else None

    region = data.get("region", "")

    flags = data.get("flags")
    flag_url = flags.get("svg") if isinstance(flags, dict) else None

    return Country(
        name=name,
        code=code,
        capital=capital,
        region=region,
        flag_url=flag_url,
    )
