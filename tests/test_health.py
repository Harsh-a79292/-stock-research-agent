"""
tests/test_health.py
────────────────────
Basic integration test for the health-check endpoint.
Run with:  pytest tests/
"""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app


@pytest.mark.asyncio
async def test_health_returns_200():
    """Health endpoint should respond with HTTP 200."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_shape():
    """Health response should include required fields."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    data = response.json()
    assert "status" in data
    assert "environment" in data
    assert "timestamp" in data
    assert "version" in data
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_root_returns_200():
    """Root endpoint should respond with HTTP 200."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
