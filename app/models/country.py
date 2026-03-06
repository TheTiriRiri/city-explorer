"""Country data models."""

from pydantic import BaseModel


class Country(BaseModel):
    """Represents a country from the RestCountries API."""

    name: str
    code: str  # ISO 3166-1 alpha-2
    capital: str | None = None
    region: str
    flag_url: str | None = None


class CountriesResponse(BaseModel):
    """Response model for the countries list endpoint."""

    count: int
    countries: list[Country]
