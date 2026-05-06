"""Pytest configuration and shared fixtures for gateway tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async HTTP client for testing the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
