"""Photo gallery data models."""

from pydantic import BaseModel


class Photo(BaseModel):
    """A single photo from Wikimedia Commons."""

    title: str
    url: str
    thumbnail_url: str | None = None
    description: str | None = None
    category: str = "other"
    mime_type: str | None = None
    commons_url: str | None = None


class PhotosResponse(BaseModel):
    """Response for the photos endpoint."""

    city: str
    photos: list[Photo] = []
    total: int = 0
