import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from gameapi.api.deps import get_db
from gameapi.api.v1.router import api_router
from gameapi.core.config import settings
from gameapi.core.database import (
    MongoDatabase,
    MongoDocument,
    get_users_collection,
)
from gameapi.db import PostgresDatabase
from gameapi.services import UserService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await MongoDatabase.connect()
    try:
        await PostgresDatabase.connect()
    except Exception:
        logger.warning("PostgreSQL is unavailable; continuing with MongoDB only", exc_info=True)
    try:
        user_service = UserService(get_users_collection())
        await user_service.ensure_indexes()
        yield
    finally:
        await PostgresDatabase.disconnect()
        await MongoDatabase.disconnect()


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
    summary="Health check for the API and MongoDB connection",
)
async def health(
    db: Annotated[AsyncIOMotorDatabase[MongoDocument], Depends(get_db)],
) -> dict[str, str]:
    try:
        await db.command("ping")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB unavailable",
        ) from None
    return {"status": "ok"}


app.include_router(api_router)
