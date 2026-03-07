"""Points of interest data models."""

from pydantic import BaseModel


class PointOfInterest(BaseModel):
    """A single point of interest near the city."""

    name: str
    category: str
    latitude: float
    longitude: float
    distance_km: float | None = None
    osm_type: str | None = None
    osm_id: int | None = None


class POIResponse(BaseModel):
    """Response for the POIs endpoint."""

    city: str
    pois: list[PointOfInterest] = []
    total: int = 0
