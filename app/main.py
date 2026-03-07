"""FastAPI application entry point with lifespan, routers, and rate limiting."""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import close_redis, init_redis
from app.utils.cache import get_redis_client
from app.utils.http import close_http_client, create_http_client


def configure_logging() -> None:
    """Configure structlog with JSON output for production, pretty-print for dev."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.upper())


configure_logging()
logger = structlog.get_logger(__name__)

# Rate limiter: 60 requests/minute per IP
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown resources."""
    logger.info("app_starting", env=settings.app_env)

    # Startup
    create_http_client()
    await init_redis()

    yield

    # Shutdown
    await close_http_client()
    await close_redis()
    logger.info("app_stopped")


app = FastAPI(
    title="City Explorer API",
    description="Aggregated city data: geography, Wikipedia descriptions, notable people, and live weather.",
    version="1.0.0",
    lifespan=lifespan,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Global exception handler for consistent error format
# ---------------------------------------------------------------------------


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Rate limit exceeded. Please try again later.",
                "detail": str(exc.detail) if hasattr(exc, "detail") else None,
            }
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
@limiter.limit("60/minute")
async def health_check(request: Request) -> dict:
    """Health check endpoint."""
    redis_client = get_redis_client()
    cache_status = "disconnected"
    if redis_client is not None:
        try:
            await redis_client.ping()
            cache_status = "connected"
        except Exception:
            cache_status = "disconnected"

    return {
        "status": "ok",
        "version": "1.0.0",
        "cache": cache_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Include routers (imported here to avoid circular imports)
# ---------------------------------------------------------------------------

from app.routers import cities, city_info, compare, countries, photos, pois, timeline  # noqa: E402

app.include_router(countries.router)
app.include_router(cities.router)
app.include_router(city_info.router)
app.include_router(compare.router)
app.include_router(photos.router)
app.include_router(timeline.router)
app.include_router(pois.router)


# ---------------------------------------------------------------------------
# SPA / static file serving (AFTER all API routes)
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def serve_spa():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
