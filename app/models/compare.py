"""City comparison data models."""

from pydantic import BaseModel

from app.models.city_info import Weather


class CityComparisonEntry(BaseModel):
    """Comparison data for a single city."""

    city: str
    country: str
    country_code: str
    population: int | None = None
    timezone: str | None = None
    weather: Weather | None = None
    famous_people_count: int = 0
    warnings: list[str] = []


class CityComparisonResponse(BaseModel):
    """Response model for the city comparison endpoint."""

    cities: list[CityComparisonEntry]
    data_sources: dict[str, str]
