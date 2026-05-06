"""Tests for the ProviderClient module."""

import json
from unittest.mock import patch

import httpx
import pytest

from gateway.config import GatewayConfig
from gateway.models import Provider
from gateway.providers import ProviderClient, ProviderResponse


@pytest.fixture
def config():
    """Default gateway config for tests."""
    return GatewayConfig(
        bedrock_region="us-east-1",
        bedrock_model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        request_timeout_seconds=30.0,
    )


@pytest.fixture
def mock_transport():
    """A mock transport for httpx that we can configure per test."""
    return httpx.MockTransport(lambda request: httpx.Response(200, json={"id": "test"}))


@pytest.fixture
def http_client(mock_transport):
    """An httpx.AsyncClient with a mock transport."""
    return httpx.AsyncClient(transport=mock_transport)


@pytest.fixture
def provider_client(config, http_client):
    """ProviderClient with mocked HTTP client."""
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-123"}):
        client = ProviderClient(config=config, http_client=http_client)
    return client


@pytest.fixture
def sample_request_body():
    """A sample chat completion request body."""
    return {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
    }


class TestProviderResponse:
    """Tests for the ProviderResponse dataclass."""

    def test_success_response(self):
        resp = ProviderResponse(status_code=200, body={"id": "test"}, is_error=False)
        assert resp.status_code == 200
        assert resp.body == {"id": "test"}
        assert resp.is_error is False

    def test_error_response(self):
        resp = ProviderResponse(status_code=500, body=None, is_error=True)
        assert resp.status_code == 500
        assert resp.is_error is True

    def test_streaming_response_has_none_body(self):
        resp = ProviderResponse(status_code=200, body=None, is_error=False)
        assert resp.body is None


class TestProviderClientBuildRequest:
    """Tests for request building logic."""

    def test_openai_url(self, provider_client):
        url, headers, body = provider_client._build_request(
            Provider.OPENAI, {"model": "gpt-4o", "messages": []}
        )
        assert url == "https://api.openai.com/v1/chat/completions"
        assert "Bearer" in headers["Authorization"]

    def test_bedrock_url(self, config):
        """Verify Bedrock URL is constructed from config."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={})
        )
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            client = ProviderClient(config=config, http_client=http_client)
        url = client._get_bedrock_url()
        assert "bedrock-runtime.us-east-1.amazonaws.com" in url
        assert "anthropic.claude-3-sonnet-20240229-v1:0" in url


class TestSendRequest:
    """Tests for send_request method."""

    @pytest.mark.anyio
    async def test_successful_openai_request(self, config, sample_request_body):
        """Test a successful request to OpenAI returns proper response."""
        response_body = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
        }
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=response_body)
        )
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        result = await client.send_request(Provider.OPENAI, sample_request_body)

        assert result.status_code == 200
        assert result.body == response_body
        assert result.is_error is False

    @pytest.mark.anyio
    async def test_5xx_response_is_error(self, config, sample_request_body):
        """Test that 5xx responses are marked as errors."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                500, json={"error": {"message": "Internal error"}}
            )
        )
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        result = await client.send_request(Provider.OPENAI, sample_request_body)

        assert result.status_code == 500
        assert result.is_error is True

    @pytest.mark.anyio
    async def test_4xx_response_is_not_error(self, config, sample_request_body):
        """Test that 4xx responses are passed through (not treated as errors)."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                429, json={"error": {"message": "Rate limited"}}
            )
        )
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        result = await client.send_request(Provider.OPENAI, sample_request_body)

        assert result.status_code == 429
        assert result.is_error is False

    @pytest.mark.anyio
    async def test_timeout_returns_error_response(self, config, sample_request_body):
        """Test that timeouts are handled gracefully."""

        def raise_timeout(request):
            raise httpx.ReadTimeout("Connection timed out")

        transport = httpx.MockTransport(raise_timeout)
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        result = await client.send_request(Provider.OPENAI, sample_request_body)

        assert result.status_code == 504
        assert result.is_error is True
        assert "timed out" in result.body["error"]["message"]

    @pytest.mark.anyio
    async def test_connect_error_returns_error_response(
        self, config, sample_request_body
    ):
        """Test that connection errors are handled gracefully."""

        def raise_connect_error(request):
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(raise_connect_error)
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        result = await client.send_request(Provider.OPENAI, sample_request_body)

        assert result.status_code == 502
        assert result.is_error is True
        assert "Connection failed" in result.body["error"]["message"]


class TestSendStreamingRequest:
    """Tests for send_streaming_request method."""

    @pytest.mark.anyio
    async def test_streaming_yields_chunks(self, config, sample_request_body):
        """Test that streaming request yields byte chunks."""
        chunks = [b"data: chunk1\n\n", b"data: chunk2\n\n", b"data: [DONE]\n\n"]

        def handler(request):
            return httpx.Response(
                200,
                stream=httpx.ByteStream(b"".join(chunks)),
            )

        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        received = []
        async for chunk in client.send_streaming_request(
            Provider.OPENAI, sample_request_body
        ):
            received.append(chunk)

        assert len(received) > 0
        combined = b"".join(received)
        assert b"chunk1" in combined

    @pytest.mark.anyio
    async def test_streaming_5xx_yields_nothing(self, config, sample_request_body):
        """Test that a 5xx during streaming yields no chunks."""

        def handler(request):
            return httpx.Response(500, content=b"Server Error")

        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        received = []
        async for chunk in client.send_streaming_request(
            Provider.OPENAI, sample_request_body
        ):
            received.append(chunk)

        assert len(received) == 0

    @pytest.mark.anyio
    async def test_streaming_timeout_yields_nothing(self, config, sample_request_body):
        """Test that a timeout during streaming yields no chunks."""

        def raise_timeout(request):
            raise httpx.ReadTimeout("Timed out")

        transport = httpx.MockTransport(raise_timeout)
        http_client = httpx.AsyncClient(transport=transport)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = ProviderClient(config=config, http_client=http_client)

        received = []
        async for chunk in client.send_streaming_request(
            Provider.OPENAI, sample_request_body
        ):
            received.append(chunk)

        assert len(received) == 0
