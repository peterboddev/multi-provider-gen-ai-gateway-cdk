"""Tests for the /health endpoint."""

from unittest.mock import patch, PropertyMock

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import app
from gateway.config import GatewayConfig
from gateway.health import HealthTracker
from gateway.models import Provider


@pytest.fixture
async def test_client():
    """Async HTTP client for testing the FastAPI application with lifespan."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    @pytest.mark.anyio
    async def test_healthy_when_both_providers_healthy(self, test_client):
        """Returns 200 with status 'healthy' when both providers are healthy."""
        config = GatewayConfig()
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.BEDROCK, 100.0)
        tracker.record_success(Provider.OPENAI, 150.0)

        with patch("gateway.app._health_tracker", tracker), \
             patch("gateway.app._config", config):
            response = await test_client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["providers"]["bedrock"]["healthy"] is True
        assert body["providers"]["openai"]["healthy"] is True

    @pytest.mark.anyio
    async def test_degraded_when_one_provider_unhealthy(self, test_client):
        """Returns 200 with status 'degraded' when one provider is unhealthy."""
        config = GatewayConfig(error_rate_threshold=0.3)
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.BEDROCK, 100.0)
        # Make openai unhealthy with high error rate
        tracker.record_failure(Provider.OPENAI)
        tracker.record_failure(Provider.OPENAI)
        tracker.record_failure(Provider.OPENAI)

        with patch("gateway.app._health_tracker", tracker), \
             patch("gateway.app._config", config):
            response = await test_client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["providers"]["bedrock"]["healthy"] is True
        assert body["providers"]["openai"]["healthy"] is False

    @pytest.mark.anyio
    async def test_unhealthy_returns_503_when_both_providers_unhealthy(self, test_client):
        """Returns 503 with status 'unhealthy' when both providers are unhealthy."""
        config = GatewayConfig(error_rate_threshold=0.3)
        tracker = HealthTracker(window_size=10)
        # Make both providers unhealthy
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.OPENAI)
        tracker.record_failure(Provider.OPENAI)

        with patch("gateway.app._health_tracker", tracker), \
             patch("gateway.app._config", config):
            response = await test_client.get("/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unhealthy"
        assert body["providers"]["bedrock"]["healthy"] is False
        assert body["providers"]["openai"]["healthy"] is False

    @pytest.mark.anyio
    async def test_healthy_when_no_data_exists(self, test_client):
        """Returns 200 with status 'healthy' when no health data exists (empty windows)."""
        config = GatewayConfig()
        tracker = HealthTracker(window_size=10)

        with patch("gateway.app._health_tracker", tracker), \
             patch("gateway.app._config", config):
            response = await test_client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["providers"]["bedrock"]["healthy"] is True
        assert body["providers"]["openai"]["healthy"] is True
        assert body["providers"]["bedrock"]["avg_latency_ms"] == 0.0
        assert body["providers"]["bedrock"]["error_rate"] == 0.0

    @pytest.mark.anyio
    async def test_response_includes_latency_and_error_rate(self, test_client):
        """Response includes avg_latency_ms and error_rate per provider."""
        config = GatewayConfig()
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.BEDROCK, 123.4)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_failure(Provider.OPENAI)
        tracker.record_success(Provider.OPENAI, 300.0)

        with patch("gateway.app._health_tracker", tracker), \
             patch("gateway.app._config", config):
            response = await test_client.get("/health")

        body = response.json()
        assert body["providers"]["bedrock"]["avg_latency_ms"] == 161.7
        assert body["providers"]["bedrock"]["error_rate"] == 0.0
        assert body["providers"]["openai"]["avg_latency_ms"] == 300.0
        assert body["providers"]["openai"]["error_rate"] == 0.5

    @pytest.mark.anyio
    async def test_response_json_structure(self, test_client):
        """Response has the expected JSON structure."""
        config = GatewayConfig()
        tracker = HealthTracker(window_size=10)

        with patch("gateway.app._health_tracker", tracker), \
             patch("gateway.app._config", config):
            response = await test_client.get("/health")

        body = response.json()
        assert "status" in body
        assert "providers" in body
        assert "bedrock" in body["providers"]
        assert "openai" in body["providers"]
        for provider_data in body["providers"].values():
            assert "healthy" in provider_data
            assert "avg_latency_ms" in provider_data
            assert "error_rate" in provider_data
