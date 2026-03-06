"""City info aggregate data models."""

from datetime import datetime

from pydantic import BaseModel


class CityDescription(BaseModel):
    """Wikipedia-sourced city description."""

    summary: str
    extract_url: str
    thumbnail_url: str | None = None


class FamousPerson(BaseModel):
    """A notable person born in the city."""

    name: str
    birth_year: int | None = None
    death_year: int | None = None
    description: str | None = None
    wikipedia_url: str


class Weather(BaseModel):
    """Current weather conditions from OpenWeatherMap."""

    temperature_celsius: float
    temperature_fahrenheit: float
    feels_like_celsius: float
    condition: str
    condition_icon: str
    humidity_percent: int
    wind_speed_kmh: float
    wind_direction: str
    visibility_km: float | None = None
    pressure_hpa: int
    uv_index: int | None = None
    sunrise: str  # HH:MM local time
    sunset: str  # HH:MM local time
    observed_at: datetime


class CityInfo(BaseModel):
    """Aggregated city profile response."""

    city: str
    country: str
    country_code: str
    coordinates: dict[str, float]
    description: CityDescription | None = None
    famous_people: list[FamousPerson] = []
    weather: Weather | None = None
    data_sources: dict[str, str]
    warnings: list[str] = []


class ErrorDetail(BaseModel):
    """Inner error detail."""

    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: ErrorDetail
