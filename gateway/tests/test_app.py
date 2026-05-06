"""Tests for the main FastAPI application request handler."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import app
from gateway.models import Provider
from gateway.providers import ProviderResponse


@pytest.fixture
def valid_request_body():
    """A valid chat completion request body."""
    return {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
    }


@pytest.fixture
def valid_streaming_request_body():
    """A valid streaming chat completion request body."""
    return {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }


@pytest.fixture
def success_response():
    """A successful provider response."""
    return ProviderResponse(
        status_code=200,
        body={
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi there!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
        is_error=False,
    )


@pytest.fixture
def error_5xx_response():
    """A 5xx error provider response."""
    return ProviderResponse(
        status_code=500,
        body={"error": {"message": "Internal server error", "type": "server_error"}},
        is_error=True,
    )


@pytest.fixture
def error_4xx_response():
    """A 4xx error provider response (rate limit)."""
    return ProviderResponse(
        status_code=429,
        body={"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}},
        is_error=False,
    )


@pytest.fixture
async def test_client():
    """Async HTTP client for testing the FastAPI application with lifespan."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestChatCompletionsValidation:
    """Test request validation (Pydantic auto-returns 422)."""

    @pytest.mark.anyio
    async def test_missing_messages_returns_422(self, test_client):
        response = await test_client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o"},
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_empty_messages_returns_422(self, test_client):
        response = await test_client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": []},
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_missing_model_returns_422(self, test_client):
        response = await test_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status_code == 422


class TestChatCompletionsSuccess:
    """Test successful request handling."""

    @pytest.mark.anyio
    async def test_successful_request_returns_provider_response(
        self, test_client, valid_request_body, success_response
    ):
        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ) as mock_health:
            mock_routing.select_provider.return_value = Provider.OPENAI
            mock_provider.send_request = AsyncMock(return_value=success_response)

            response = await test_client.post(
                "/v1/chat/completions", json=valid_request_body
            )

            assert response.status_code == 200
            body = response.json()
            assert body["id"] == "chatcmpl-123"
            assert body["choices"][0]["message"]["content"] == "Hi there!"
            mock_health.record_success.assert_called_once()

    @pytest.mark.anyio
    async def test_successful_request_records_health_metrics(
        self, test_client, valid_request_body, success_response
    ):
        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ) as mock_health:
            mock_routing.select_provider.return_value = Provider.BEDROCK
            mock_provider.send_request = AsyncMock(return_value=success_response)

            await test_client.post("/v1/chat/completions", json=valid_request_body)

            mock_health.record_success.assert_called_once()
            call_args = mock_health.record_success.call_args
            assert call_args[0][0] == Provider.BEDROCK
            assert call_args[0][1] > 0  # latency_ms > 0


class TestChatCompletionsFailover:
    """Test failover behavior on provider failure."""

    @pytest.mark.anyio
    async def test_failover_on_5xx_retries_with_fallback(
        self, test_client, valid_request_body, error_5xx_response, success_response
    ):
        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ) as mock_health:
            mock_routing.select_provider.return_value = Provider.BEDROCK
            mock_routing.get_fallback_provider.return_value = Provider.OPENAI
            mock_provider.send_request = AsyncMock(
                side_effect=[error_5xx_response, success_response]
            )

            response = await test_client.post(
                "/v1/chat/completions", json=valid_request_body
            )

            assert response.status_code == 200
            mock_health.record_failure.assert_called_once_with(Provider.BEDROCK)
            mock_health.record_success.assert_called_once()

    @pytest.mark.anyio
    async def test_both_providers_fail_returns_502(
        self, test_client, valid_request_body, error_5xx_response
    ):
        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ) as mock_health:
            mock_routing.select_provider.return_value = Provider.BEDROCK
            mock_routing.get_fallback_provider.return_value = Provider.OPENAI
            mock_provider.send_request = AsyncMock(
                side_effect=[error_5xx_response, error_5xx_response]
            )

            response = await test_client.post(
                "/v1/chat/completions", json=valid_request_body
            )

            assert response.status_code == 502
            body = response.json()
            assert body["error"]["message"] == "All providers unavailable"
            assert body["error"]["type"] == "server_error"
            assert mock_health.record_failure.call_count == 2


class TestChatCompletions4xxPassthrough:
    """Test that 4xx errors are passed through without retry."""

    @pytest.mark.anyio
    async def test_4xx_passed_through_no_retry(
        self, test_client, valid_request_body, error_4xx_response
    ):
        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ) as mock_health:
            mock_routing.select_provider.return_value = Provider.OPENAI
            mock_provider.send_request = AsyncMock(return_value=error_4xx_response)

            response = await test_client.post(
                "/v1/chat/completions", json=valid_request_body
            )

            assert response.status_code == 429
            body = response.json()
            assert body["error"]["message"] == "Rate limit exceeded"
            # No retry, no health recording
            mock_routing.get_fallback_provider.assert_not_called()
            mock_health.record_failure.assert_not_called()
            mock_health.record_success.assert_not_called()


class TestChatCompletionsStreaming:
    """Test streaming (SSE) request handling."""

    @pytest.mark.anyio
    async def test_streaming_request_returns_sse(
        self, test_client, valid_streaming_request_body
    ):
        async def mock_stream(*args, **kwargs):
            yield b"data: {\"chunk\": 1}\n\n"
            yield b"data: {\"chunk\": 2}\n\n"

        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ) as mock_health:
            mock_routing.select_provider.return_value = Provider.OPENAI
            mock_provider.send_streaming_request = MagicMock(return_value=mock_stream())

            response = await test_client.post(
                "/v1/chat/completions", json=valid_streaming_request_body
            )

            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            mock_health.record_success.assert_called_once()

    @pytest.mark.anyio
    async def test_streaming_fallback_on_no_chunks(
        self, test_client, valid_streaming_request_body
    ):
        async def empty_stream(*args, **kwargs):
            return
            yield  # noqa: make it an async generator

        async def fallback_stream(*args, **kwargs):
            yield b"data: {\"chunk\": 1}\n\n"

        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ) as mock_health:
            mock_routing.select_provider.return_value = Provider.BEDROCK
            mock_routing.get_fallback_provider.return_value = Provider.OPENAI
            mock_provider.send_streaming_request = MagicMock(
                side_effect=[empty_stream(), fallback_stream()]
            )

            response = await test_client.post(
                "/v1/chat/completions", json=valid_streaming_request_body
            )

            assert response.status_code == 200
            mock_health.record_failure.assert_called_once_with(Provider.BEDROCK)
            mock_health.record_success.assert_called_once()


class TestStructuredLogging:
    """Test structured JSON log emission."""

    @pytest.mark.anyio
    async def test_successful_request_emits_log(
        self, test_client, valid_request_body, success_response, caplog
    ):
        import logging

        with patch(
            "gateway.app._routing_engine"
        ) as mock_routing, patch(
            "gateway.app._provider_client"
        ) as mock_provider, patch(
            "gateway.app._health_tracker"
        ):
            mock_routing.select_provider.return_value = Provider.OPENAI
            mock_provider.send_request = AsyncMock(return_value=success_response)

            with caplog.at_level(logging.INFO, logger="gateway.app"):
                await test_client.post(
                    "/v1/chat/completions", json=valid_request_body
                )

            # Find the structured log entry
            log_entries = [
                r for r in caplog.records if r.name == "gateway.app"
            ]
            assert len(log_entries) >= 1
            log_data = json.loads(log_entries[0].message)
            assert "provider" in log_data
            assert "latency_ms" in log_data
            assert "status_code" in log_data
            assert "timestamp" in log_data
            assert log_data["provider"] == "openai"
            assert log_data["status_code"] == 200
