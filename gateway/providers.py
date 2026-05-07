"""Provider Client module.

Handles HTTP communication with backend providers (AWS Bedrock and OpenAI).
Supports both synchronous and streaming request modes.
"""

import logging
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session as BotocoreSession

from gateway.config import GatewayConfig
from gateway.models import Provider

logger = logging.getLogger(__name__)

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


@dataclass
class ProviderResponse:
    """Response from a provider request."""

    status_code: int
    body: dict | None  # None for streaming
    is_error: bool


class ProviderClient:
    """Handles HTTP communication with backend LLM providers.

    Supports AWS Bedrock (via OpenAI-compatible API with SigV4 auth)
    and OpenAI (with Bearer token auth). Handles both synchronous
    and streaming (SSE) request modes.
    """

    def __init__(self, config: GatewayConfig, http_client: httpx.AsyncClient):
        self._config = config
        self._http_client = http_client
        self._openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self._botocore_session = BotocoreSession()

    def _get_bedrock_url(self) -> str:
        """Construct the Bedrock OpenAI-compatible Chat Completions endpoint URL."""
        region = self._config.bedrock_region
        model_id = self._config.bedrock_model_id
        return (
            f"https://bedrock-runtime.{region}.amazonaws.com"
            f"/model/{model_id}/chat/completions"
        )

    def _sign_bedrock_request(
        self, method: str, url: str, headers: dict, body: bytes
    ) -> dict:
        """Sign a request for AWS Bedrock using SigV4.

        Returns the headers dict with added authorization headers.
        """
        credentials = self._botocore_session.get_credentials()
        if credentials is None:
            raise RuntimeError("AWS credentials not available for Bedrock signing")

        aws_request = AWSRequest(
            method=method,
            url=url,
            headers=headers,
            data=body,
        )
        SigV4Auth(
            credentials.get_frozen_credentials(),
            "bedrock",
            self._config.bedrock_region,
        ).add_auth(aws_request)

        return dict(aws_request.headers)

    def _get_openai_headers(self) -> dict:
        """Get headers for OpenAI API requests."""
        return {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }

    def _build_request(
        self, provider: Provider, request_body: dict
    ) -> tuple[str, dict, bytes]:
        """Build the URL, headers, and encoded body for a provider request.

        Returns:
            Tuple of (url, headers, body_bytes)
        """
        import json

        if provider == Provider.BEDROCK:
            # Override model field with the configured Bedrock model/inference profile ID
            bedrock_body = {**request_body, "model": self._config.bedrock_model_id}
            body_bytes = json.dumps(bedrock_body).encode("utf-8")
            url = self._get_bedrock_url()
            headers = {"Content-Type": "application/json"}
            signed_headers = self._sign_bedrock_request(
                "POST", url, headers, body_bytes
            )
            return url, signed_headers, body_bytes
        else:
            # Override model field with the configured OpenAI model
            openai_body = {**request_body, "model": self._config.openai_model}
            body_bytes = json.dumps(openai_body).encode("utf-8")
            url = OPENAI_CHAT_COMPLETIONS_URL
            headers = self._get_openai_headers()
            return url, headers, body_bytes

    async def send_request(
        self, provider: Provider, request_body: dict
    ) -> ProviderResponse:
        """Send a chat completion request to the specified provider.

        Handles timeouts and connection errors, returning a ProviderResponse
        with is_error=True for server errors and connectivity issues.
        4xx responses are passed through (is_error=False).
        """
        try:
            url, headers, body_bytes = self._build_request(provider, request_body)

            response = await self._http_client.post(
                url,
                content=body_bytes,
                headers=headers,
                timeout=self._config.request_timeout_seconds,
            )

            is_error = response.status_code >= 500
            body = response.json()

            return ProviderResponse(
                status_code=response.status_code,
                body=body,
                is_error=is_error,
            )

        except httpx.TimeoutException:
            logger.warning("Timeout connecting to provider %s", provider.value)
            return ProviderResponse(
                status_code=504,
                body={"error": {"message": "Request timed out", "type": "timeout_error"}},
                is_error=True,
            )
        except httpx.ConnectError:
            logger.warning("Connection error for provider %s", provider.value)
            return ProviderResponse(
                status_code=502,
                body={"error": {"message": "Connection failed", "type": "connection_error"}},
                is_error=True,
            )

    async def send_streaming_request(
        self, provider: Provider, request_body: dict
    ) -> AsyncGenerator[bytes, None]:
        """Send a streaming chat completion request. Yields SSE chunks.

        Yields raw bytes from the SSE stream. The caller handles formatting.
        On error, yields an error event and stops.
        """
        try:
            url, headers, body_bytes = self._build_request(provider, request_body)

            async with self._http_client.stream(
                "POST",
                url,
                content=body_bytes,
                headers=headers,
                timeout=self._config.request_timeout_seconds,
            ) as response:
                if response.status_code >= 500:
                    logger.warning(
                        "Streaming error from provider %s: %d",
                        provider.value,
                        response.status_code,
                    )
                    return

                async for chunk in response.aiter_bytes():
                    yield chunk

        except httpx.TimeoutException:
            logger.warning("Streaming timeout for provider %s", provider.value)
            return
        except httpx.ConnectError:
            logger.warning("Streaming connection error for provider %s", provider.value)
            return
