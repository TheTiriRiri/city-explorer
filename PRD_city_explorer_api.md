# Product Requirements Document: City Explorer REST API

## Project Overview

**Project Name:** City Explorer API  
**Version:** 1.0  
**Language:** Python  
**Type:** REST API  
**Purpose:** Provide structured, aggregated information about cities worldwide — including geographic data, Wikipedia-sourced descriptions, notable people born there, and real-time weather conditions.

---

## Goals

- Build a clean, well-documented Python REST API that aggregates city data from multiple sources.
- Allow users to browse countries and cities, then retrieve enriched city profiles.
- Deliver real-time weather alongside historical/cultural context for any given city.
- Keep the codebase modular, testable, and extensible for future data sources.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Framework | FastAPI |
| HTTP Client | httpx (async) |
| Data validation | Pydantic v2 |
| Caching | Redis (via `redis-py`) |
| Testing | pytest + pytest-asyncio |
| Documentation | Auto-generated via FastAPI / Swagger UI |
| Config management | python-dotenv + Pydantic Settings |
| Logging | Python `logging` + structlog |

---

## External APIs & Data Sources

| Source | Purpose | Auth |
|---|---|---|
| RestCountries API (`restcountries.com`) | List all countries, country metadata | None (free) |
| GeoNames API (`geonames.org`) | List cities within a country, coordinates | Free account + username |
| Wikipedia REST API (`en.wikipedia.org/api/rest_v1`) | City description / summary | None (free) |
| Wikipedia API (Action API) | Famous people born in city | None (free) |
| OpenWeatherMap API | Current weather for city | API Key (free tier) |

> **Note for Claude Code:** All API keys must be stored in a `.env` file and never hardcoded. Use `pydantic-settings` to load them.

---

## Project Structure

```
city-explorer-api/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings via pydantic-settings
│   ├── dependencies.py          # Shared DI (cache client, http client)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── countries.py         # GET /countries
│   │   ├── cities.py            # GET /countries/{code}/cities
│   │   └── city_info.py         # GET /city/{city_name}/info
│   ├── services/
│   │   ├── __init__.py
│   │   ├── countries_service.py
│   │   ├── cities_service.py
│   │   ├── wikipedia_service.py
│   │   └── weather_service.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── country.py
│   │   ├── city.py
│   │   └── city_info.py
│   └── utils/
│       ├── __init__.py
│       ├── cache.py             # Redis caching decorator/helpers
│       └── http.py              # Shared async HTTP client
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_countries.py
│   ├── test_cities.py
│   └── test_city_info.py
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## API Endpoints Specification

### 1. `GET /countries`

**Description:** Returns a list of all available countries.

**Query Parameters:**

| Param | Type | Required | Description |
|---|---|---|---|
| `search` | string | No | Filter countries by name (case-insensitive partial match) |

**Response `200 OK`:**
```json
{
  "count": 195,
  "countries": [
    {
      "name": "Poland",
      "code": "PL",
      "capital": "Warsaw",
      "region": "Europe",
      "flag_url": "https://flagcdn.com/pl.svg"
    }
  ]
}
```

**Caching:** 24 hours (country list changes rarely).

---

### 2. `GET /countries/{country_code}/cities`

**Description:** Returns a paginated list of cities for the given ISO 3166-1 alpha-2 country code.

**Path Parameters:**

| Param | Type | Required | Description |
|---|---|---|---|
| `country_code` | string | Yes | ISO 3166-1 alpha-2 (e.g. `PL`, `US`, `DE`) |

**Query Parameters:**

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `search` | string | No | — | Filter cities by name |
| `page` | int | No | 1 | Page number |
| `per_page` | int | No | 20 | Results per page (max 100) |

**Response `200 OK`:**
```json
{
  "country_code": "PL",
  "country_name": "Poland",
  "total": 312,
  "page": 1,
  "per_page": 20,
  "cities": [
    {
      "name": "Kraków",
      "latitude": 50.0647,
      "longitude": 19.945,
      "population": 779966,
      "timezone": "Europe/Warsaw"
    }
  ]
}
```

**Error `404`:** Country code not found.  
**Caching:** 12 hours per country.

---

### 3. `GET /city/{city_name}/info`

**Description:** Returns full city profile: description, famous people, and current weather.

**Path Parameters:**

| Param | Type | Required | Description |
|---|---|---|---|
| `city_name` | string | Yes | City name (URL-encoded if spaces) |

**Query Parameters:**

| Param | Type | Required | Description |
|---|---|---|---|
| `country_code` | string | No | Disambiguate cities with the same name (e.g. `Springfield, US`) |

**Response `200 OK`:**
```json
{
  "city": "Kraków",
  "country": "Poland",
  "country_code": "PL",
  "coordinates": {
    "latitude": 50.0647,
    "longitude": 19.945
  },
  "description": {
    "summary": "Kraków is the second-largest and one of the oldest cities in Poland...",
    "extract_url": "https://en.wikipedia.org/wiki/Krak%C3%B3w",
    "thumbnail_url": "https://upload.wikimedia.org/wikipedia/commons/..."
  },
  "famous_people": [
    {
      "name": "Pope John Paul II",
      "birth_year": 1920,
      "death_year": 2005,
      "description": "Head of the Catholic Church from 1978 to 2005.",
      "wikipedia_url": "https://en.wikipedia.org/wiki/Pope_John_Paul_II"
    },
    {
      "name": "Wisława Szymborska",
      "birth_year": 1923,
      "death_year": 2012,
      "description": "Polish poet and Nobel Prize laureate.",
      "wikipedia_url": "https://en.wikipedia.org/wiki/Wis%C5%82awa_Szymborska"
    }
  ],
  "weather": {
    "temperature_celsius": 12.4,
    "temperature_fahrenheit": 54.3,
    "feels_like_celsius": 10.1,
    "condition": "Partly cloudy",
    "condition_icon": "https://openweathermap.org/img/wn/02d@2x.png",
    "humidity_percent": 68,
    "wind_speed_kmh": 15.3,
    "wind_direction": "NW",
    "visibility_km": 10.0,
    "pressure_hpa": 1012,
    "uv_index": 3,
    "sunrise": "06:12",
    "sunset": "18:45",
    "observed_at": "2025-03-06T10:30:00Z"
  },
  "data_sources": {
    "description": "Wikipedia",
    "famous_people": "Wikipedia",
    "weather": "OpenWeatherMap"
  }
}
```

**Error `404`:** City not found.  
**Error `422`:** Validation error (invalid params).  
**Error `503`:** One or more upstream APIs unavailable (partial data still returned if possible).

**Caching:**
- Description + famous people: 24 hours
- Weather: 10 minutes

---

### 4. `GET /health`

**Description:** Health check endpoint.

**Response `200 OK`:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "cache": "connected",
  "timestamp": "2025-03-06T10:30:00Z"
}
```

---

## Data Models (Pydantic)

### `Country`
```python
class Country(BaseModel):
    name: str
    code: str           # ISO 3166-1 alpha-2
    capital: str | None
    region: str
    flag_url: str | None
```

### `City`
```python
class City(BaseModel):
    name: str
    latitude: float
    longitude: float
    population: int | None
    timezone: str | None
```

### `CityDescription`
```python
class CityDescription(BaseModel):
    summary: str
    extract_url: str
    thumbnail_url: str | None
```

### `FamousPerson`
```python
class FamousPerson(BaseModel):
    name: str
    birth_year: int | None
    death_year: int | None
    description: str | None
    wikipedia_url: str
```

### `Weather`
```python
class Weather(BaseModel):
    temperature_celsius: float
    temperature_fahrenheit: float
    feels_like_celsius: float
    condition: str
    condition_icon: str
    humidity_percent: int
    wind_speed_kmh: float
    wind_direction: str
    visibility_km: float | None
    pressure_hpa: int
    uv_index: int | None
    sunrise: str          # HH:MM local time
    sunset: str           # HH:MM local time
    observed_at: datetime
```

### `CityInfo` (aggregated response)
```python
class CityInfo(BaseModel):
    city: str
    country: str
    country_code: str
    coordinates: dict[str, float]
    description: CityDescription
    famous_people: list[FamousPerson]
    weather: Weather
    data_sources: dict[str, str]
```

---

## Service Layer Details

### `wikipedia_service.py`

**City Description:**
- Call `GET https://en.wikipedia.org/api/rest_v1/page/summary/{city_name}`
- Extract `extract` (plain text summary), `content_urls.desktop.page`, `thumbnail.source`
- Fallback: if city not found, try `{city_name}_(city)`

**Famous People (born in city):**
- Use Wikipedia Action API with SPARQL-like category query:
  - `GET https://en.wikipedia.org/w/api.php?action=query&list=categorymembers&cmtitle=Category:People_from_{city_name}&cmlimit=20&format=json`
- For each result, call the summary endpoint to get birth year and short description
- Filter out non-person articles (check for `type: "standard"` and presence of birth/death year patterns)
- Limit to top 10 notable people (sort by Wikipedia page views if possible)

### `weather_service.py`

- Call `GET https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={API_KEY}&units=metric`
- Also fetch `onecall` endpoint for UV index and sunrise/sunset
- Convert wind degrees to cardinal direction string (N, NE, E, SE, S, SW, W, NW)
- Convert m/s to km/h for wind speed
- Calculate Fahrenheit from Celsius

### `countries_service.py`

- Call `GET https://restcountries.com/v3.1/all?fields=name,cca2,capital,region,flags`
- Cache full list; filter in-memory for search

### `cities_service.py`

- Call GeoNames API: `GET http://api.geonames.org/searchJSON?country={code}&featureClass=P&maxRows=1000&username={USERNAME}&orderby=population`
- Returns cities sorted by population descending

---

## Caching Strategy

Use Redis with TTL-based invalidation. Implement a `@cached(ttl=seconds)` decorator in `utils/cache.py`.

Cache key patterns:
```
city_explorer:countries:all
city_explorer:countries:search:{query}
city_explorer:cities:{country_code}
city_explorer:wiki:description:{city_name}
city_explorer:wiki:people:{city_name}
city_explorer:weather:{city_name}:{country_code}
```

If Redis is unavailable, the API must degrade gracefully (log a warning, skip cache, fetch live).

---

## Error Handling

All errors must return a consistent JSON structure:

```json
{
  "error": {
    "code": "CITY_NOT_FOUND",
    "message": "City 'Xyzzy' could not be found.",
    "detail": null
  }
}
```

**Error codes:**

| Code | HTTP Status | Scenario |
|---|---|---|
| `CITY_NOT_FOUND` | 404 | City not in GeoNames or Wikipedia |
| `COUNTRY_NOT_FOUND` | 404 | Unknown country code |
| `UPSTREAM_ERROR` | 503 | External API unavailable |
| `RATE_LIMITED` | 429 | Rate limit exceeded |
| `VALIDATION_ERROR` | 422 | Invalid query/path params |

For `GET /city/{city_name}/info`, if one upstream fails (e.g., weather), return partial data with a `warnings` array:

```json
{
  "city": "Kraków",
  "weather": null,
  "warnings": ["Weather data temporarily unavailable."],
  ...
}
```

---

## Configuration (`.env.example`)

```env
# App
APP_ENV=development
APP_PORT=8000
LOG_LEVEL=INFO

# Redis
REDIS_URL=redis://localhost:6379/0

# External APIs
OPENWEATHERMAP_API_KEY=your_key_here
GEONAMES_USERNAME=your_username_here

# Cache TTLs (seconds)
CACHE_TTL_COUNTRIES=86400
CACHE_TTL_CITIES=43200
CACHE_TTL_WIKI=86400
CACHE_TTL_WEATHER=600
```

---

## Testing Requirements

Each service must have unit tests with mocked HTTP responses. Use `pytest-asyncio` for async tests and `respx` to mock `httpx` calls.

**Minimum test coverage: 80%**

Test cases to implement:
- `test_countries.py`: list countries, search filter, invalid search
- `test_cities.py`: valid country code, invalid country code, pagination, search
- `test_city_info.py`:
  - Happy path (all data available)
  - Wikipedia not found (graceful degradation)
  - Weather API failure (partial response with warning)
  - Ambiguous city name resolved via `country_code` param
  - Cache hit vs. cache miss behavior

---

## Non-Functional Requirements

| Requirement | Target |
|---|---|
| Response time (p95) | < 800 ms (cache hit < 50 ms) |
| Availability | 99.5% |
| Upstream timeouts | 5s per external API call |
| Concurrent requests | Handle 100 req/s minimum |
| Rate limiting | 60 req/min per IP (use `slowapi`) |

---

## Implementation Notes for Claude Code

1. **Start with `app/config.py`** and `app/main.py` to establish the FastAPI app scaffold and settings.
2. **Implement services one by one**: countries → cities → wikipedia → weather.
3. **Wire routers** after services are tested.
4. **Add caching last**, after logic is confirmed correct.
5. **Use `asyncio.gather()`** in the `/city/{city_name}/info` handler to fetch Wikipedia and weather in parallel.
6. **GeoNames is HTTP only** — ensure no SSL enforcement for that client.
7. Wikipedia's category-member API can return non-people articles; add a secondary filter checking if the article extract mentions birth.
8. The `restcountries.com` v3.1 API uses nested objects — map `name.common` to `name` and `cca2` to `code`.
9. Flag images from RestCountries use CDN format: `https://flagcdn.com/{code_lowercase}.svg`.

---

## Deliverables Checklist

- [ ] Fully functional FastAPI application
- [ ] All 4 endpoints implemented and tested
- [ ] `.env.example` with all required variables
- [ ] `requirements.txt` and `requirements-dev.txt`
- [ ] Redis caching with graceful fallback
- [ ] Parallel upstream fetching with `asyncio.gather`
- [ ] Consistent error handling and partial responses
- [ ] Pytest test suite with ≥80% coverage
- [ ] Auto-generated Swagger UI at `/docs`
- [ ] `README.md` with setup and run instructions

---

*Generated for use with Claude Code CLI. Pass this document as the project context at session start.*
