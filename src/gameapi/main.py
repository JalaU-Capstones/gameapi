import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from gameapi.api.deps import SessionDep
from gameapi.api.v1.router import api_router as v1_router
from gameapi.api.v2.router import api_router as v2_router
from gameapi.core.config import settings
from gameapi.core.rate_limit import limiter
from gameapi.db import PostgresDatabase
from gameapi.services.event_bus import event_bus
from gameapi.services.log_service import LogService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await PostgresDatabase.connect()

    log_service = LogService(
        PostgresDatabase.session_factory(),
        buffer_size=settings.log.buffer_size,
        flush_interval=settings.log.flush_interval_seconds,
        retention_days=settings.log.retention_days,
        queue_maxsize=settings.log.queue_maxsize,
    )
    await log_service.start()

    root_logger = logging.getLogger()
    root_logger.addHandler(log_service.get_handler())
    root_logger.setLevel(logging.INFO)

    _.state.log_service = log_service

    try:
        yield
    finally:
        root_logger.removeHandler(log_service.get_handler())
        await log_service.stop()
        await event_bus.shutdown()
        await PostgresDatabase.disconnect()


app = FastAPI(
    title="Game API",
    version="v1",
    description="REST API for user and gameplay basic management",
    lifespan=lifespan,
)


async def _rate_limit_handler(
    request: Request,
    exc: Exception,
) -> Response:
    """Return a consistent 429 payload while preserving the rate-limit headers."""
    del exc
    response: Response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"message": "Too many requests. Please slow down."},
    )
    limiter_instance = request.app.state.limiter
    view_rate_limit = getattr(request.state, "view_rate_limit", None)
    if view_rate_limit is not None:
        response = limiter_instance._inject_headers(response, view_rate_limit)
    return response


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

# Cookies require credentials and an explicit origin list when browser-based clients are used.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = f"{location}: {first.get('msg', 'Invalid request')}".strip(": ")
    else:
        message = "Invalid request"
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"message": message},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    _: Request,
    exc: HTTPException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check for the API and PostgreSQL connection",
)
async def health(session: SessionDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL unavailable",
        ) from None
    return {"status": "ok"}


app.include_router(v1_router)
app.include_router(v2_router)
