"""City data models."""

from pydantic import BaseModel


class City(BaseModel):
    """Represents a city from the GeoNames API."""

    name: str
    latitude: float
    longitude: float
    population: int | None = None
    timezone: str | None = None


class CitiesResponse(BaseModel):
    """Response model for the cities list endpoint."""

    country_code: str
    country_name: str
    total: int
    page: int
    per_page: int
    cities: list[City]
