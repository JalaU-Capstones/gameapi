import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from gameapi.api.deps import SessionDep
from gameapi.api.v1.router import api_router
from gameapi.core.config import settings
from gameapi.db import PostgresDatabase

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await PostgresDatabase.connect()
    try:
        yield
    finally:
        await PostgresDatabase.disconnect()


app = FastAPI(
    title="Game API",
    version="v1",
    description="REST API for user and gameplay basic management",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=False,
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


app.include_router(api_router)
