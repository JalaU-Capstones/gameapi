import importlib
import sys
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

import gameapi.main as main_module
from gameapi.api.deps import get_session
from gameapi.core.config import settings


class _DummySession:
    async def execute(self, *_args, **_kwargs):
        return None


class _BrokenSession:
    async def execute(self, *_args, **_kwargs):
        raise RuntimeError("db failure")


def _override_db_session() -> None:
    async def _session() -> AsyncIterator[_DummySession]:
        yield _DummySession()

    main_module.app.dependency_overrides[get_session] = _session


def _no_lifespan(app):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _inner():
        yield

    return _inner()


@pytest.mark.asyncio
async def test_rate_limit_handler_injects_headers_when_view_limit_present() -> None:
    limiter = SimpleNamespace(_inject_headers=lambda response, value: response)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(limiter=limiter)),
        state=SimpleNamespace(view_rate_limit="test"),
    )

    response = await main_module._rate_limit_handler(request, RuntimeError("boom"))

    assert response.status_code == 429


@pytest.mark.asyncio
async def test_validation_exception_handler_handles_empty_error_list() -> None:
    response = await main_module.validation_exception_handler(
        SimpleNamespace(),
        RequestValidationError([]),
    )

    assert response.status_code == 400
    assert response.body


@pytest.mark.asyncio
async def test_health_returns_503_after_database_error() -> None:
    with pytest.raises(HTTPException, match="PostgreSQL unavailable"):
        await main_module.health(_BrokenSession())


def test_metrics_disabled_by_default(monkeypatch) -> None:
    sys.modules.pop("prometheus_fastapi_instrumentator", None)
    monkeypatch.setattr(settings.metrics, "enabled", False)
    importlib.reload(main_module)
    main_module.app.router.lifespan_context = _no_lifespan
    _override_db_session()
    try:
        with TestClient(main_module.app) as client:
            response = client.get("/metrics")
            assert response.status_code == 404
            assert client.get("/health").status_code == 200
            assert "prometheus_fastapi_instrumentator" not in sys.modules
    finally:
        main_module.app.dependency_overrides.clear()
        monkeypatch.setattr(settings.metrics, "enabled", False)
        importlib.reload(main_module)


def test_metrics_enabled_exposes_and_excludes_endpoints(monkeypatch) -> None:
    monkeypatch.setattr(settings.metrics, "enabled", True)
    importlib.reload(main_module)
    main_module.app.router.lifespan_context = _no_lifespan
    _override_db_session()
    try:
        with TestClient(main_module.app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/health").status_code == 200

            assert client.get("/metrics").status_code == 200
            assert client.get("/metrics").status_code == 200

            response = client.get("/metrics")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/plain")
            body = response.text
            assert "http_requests_total" in body
            assert 'handler="/metrics"' not in body
            assert 'handler="/health"' not in body
    finally:
        main_module.app.dependency_overrides.clear()
        monkeypatch.setattr(settings.metrics, "enabled", False)
        importlib.reload(main_module)
