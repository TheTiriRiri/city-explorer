"""Nearby cities data models."""

from pydantic import BaseModel


class Coordinates(BaseModel):
    """Geographic coordinates."""

    latitude: float
    longitude: float


class NearbyCityEntry(BaseModel):
    """A single nearby city."""

    city: str
    country: str
    country_code: str
    population: int | None = None
    timezone: str | None = None
    distance_km: float
    coordinates: Coordinates


class NearbyCitiesResponse(BaseModel):
    """Response model for the nearby cities endpoint."""

    origin_city: str
    origin_country: str
    origin_coordinates: Coordinates
    radius_km: int
    nearby_cities: list[NearbyCityEntry]
    total: int
