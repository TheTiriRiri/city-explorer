"""Weather service – fetches current weather from OpenWeatherMap."""

from datetime import datetime, timezone, timedelta

import httpx
import structlog

from app.models.city_info import Weather

logger = structlog.get_logger(__name__)

_OPENWEATHERMAP_URL = "https://api.openweathermap.org/data/2.5/weather"

_CARDINAL_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _degrees_to_cardinal(degrees: float) -> str:
    """Convert wind direction in degrees to a cardinal compass direction."""
    # Each cardinal direction covers a 45-degree arc centred on its heading.
    index = round(degrees / 45) % 8
    return _CARDINAL_DIRECTIONS[index]


def _unix_to_local_hhmm(unix_ts: int, utc_offset_seconds: int) -> str:
    """Convert a Unix timestamp to HH:MM in the location's local time."""
    tz = timezone(timedelta(seconds=utc_offset_seconds))
    dt = datetime.fromtimestamp(unix_ts, tz=tz)
    return dt.strftime("%H:%M")


async def get_weather(
    client: httpx.AsyncClient,
    city_name: str,
    api_key: str,
    country_code: str | None = None,
) -> Weather:
    """Fetch current weather for *city_name* and return a ``Weather`` model.

    Parameters
    ----------
    client:
        Shared ``httpx.AsyncClient`` (managed by the application lifespan).
    city_name:
        City name to query (e.g. ``"London"``).
    api_key:
        OpenWeatherMap API key.
    country_code:
        Optional ISO-3166 country code to disambiguate city names.

    Raises
    ------
    httpx.HTTPStatusError
        If the upstream API returns a non-2xx response.
    httpx.HTTPError
        On network / timeout errors.
    """
    q = f"{city_name},{country_code}" if country_code else city_name

    params: dict[str, str] = {
        "q": q,
        "appid": api_key,
        "units": "metric",
    }

    log = logger.bind(city=city_name, country_code=country_code)
    log.info("weather_request_start")

    try:
        response = await client.get(_OPENWEATHERMAP_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError:
        log.error(
            "weather_request_http_error",
            status_code=response.status_code,
            body=response.text[:500],
        )
        raise
    except httpx.HTTPError as exc:
        log.error("weather_request_network_error", error=str(exc))
        raise

    data = response.json()
    log.info("weather_request_success")

    # --- Map response to Weather model ---
    main = data["main"]
    wind = data.get("wind", {})
    weather_block = data["weather"][0]
    sys_block = data.get("sys", {})
    tz_offset = data.get("timezone", 0)

    temp_c: float = main["temp"]
    temp_f: float = round(temp_c * 9 / 5 + 32, 1)

    visibility_raw = data.get("visibility")
    visibility_km: float | None = (
        round(visibility_raw / 1000, 1) if visibility_raw is not None else None
    )

    icon_code = weather_block.get("icon", "01d")

    return Weather(
        temperature_celsius=temp_c,
        temperature_fahrenheit=temp_f,
        feels_like_celsius=main["feels_like"],
        condition=weather_block["description"].capitalize(),
        condition_icon=f"https://openweathermap.org/img/wn/{icon_code}@2x.png",
        humidity_percent=main["humidity"],
        wind_speed_kmh=round(wind.get("speed", 0) * 3.6, 1),
        wind_direction=_degrees_to_cardinal(wind.get("deg", 0)),
        visibility_km=visibility_km,
        pressure_hpa=main["pressure"],
        uv_index=None,
        sunrise=_unix_to_local_hhmm(sys_block["sunrise"], tz_offset),
        sunset=_unix_to_local_hhmm(sys_block["sunset"], tz_offset),
        observed_at=datetime.now(timezone.utc),
    )
