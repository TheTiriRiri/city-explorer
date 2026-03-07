"""Historical timeline data models."""

from pydantic import BaseModel


class HistoricalEvent(BaseModel):
    """A single historical event."""

    year: int
    event: str


class TimelineResponse(BaseModel):
    """Response for the timeline endpoint."""

    city: str
    events: list[HistoricalEvent] = []
    total: int = 0
