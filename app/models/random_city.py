"""Random city discovery data models."""

from pydantic import BaseModel


class Coordinates(BaseModel):
    """Geographic coordinates."""

    latitude: float
    longitude: float


class RandomCityResponse(BaseModel):
    """Response model for the random city endpoint."""

    city: str
    country: str
    country_code: str
    coordinates: Coordinates
    population: int | None = None
    timezone: str | None = None
    data_sources: dict[str, str]
