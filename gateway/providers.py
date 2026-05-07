"""Provider Client module.

Bedrock: Uses bedrock-runtime invoke-model with Anthropic Messages format,
         translates response to OpenAI Chat Completions format.
OpenAI:  Direct call to api.openai.com/v1/chat/completions.
"""

import json
import logging
import os
import time
import uuid
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
    body: dict | None
    is_error: bool


def _bedrock_to_openai_response(bedrock_response: dict) -> dict:
    """Translate Anthropic Messages response to OpenAI Chat Completions format."""
    content = ""
    if bedrock_response.get("content"):
        content = "".join(
            block.get("text", "") for block in bedrock_response["content"]
            if block.get("type") == "text"
        )

    usage = bedrock_response.get("usage", {})
    return {
        "id": f"chatcmpl-{bedrock_response.get('id', uuid.uuid4().hex[:24])}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": bedrock_response.get("model", "bedrock"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": _map_stop_reason(bedrock_response.get("stop_reason")),
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


def _map_stop_reason(stop_reason: str | None) -> str:
    """Map Anthropic stop_reason to OpenAI finish_reason."""
    mapping = {
        "end_turn": "stop",
        "max_tokens": "length",
        "stop_sequence": "stop",
    }
    return mapping.get(stop_reason, "stop")


def _openai_to_bedrock_request(request_body: dict, model_id: str) -> dict:
    """Translate OpenAI Chat Completions request to Anthropic Messages format."""
    messages = request_body.get("messages", [])

    # Extract system message if present
    system_messages = [m for m in messages if m.get("role") == "system"]
    non_system_messages = [m for m in messages if m.get("role") != "system"]

    bedrock_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": non_system_messages,
        "max_tokens": request_body.get("max_tokens", 4096),
    }

    if system_messages:
        bedrock_body["system"] = system_messages[0].get("content", "")

    if request_body.get("temperature") is not None:
        bedrock_body["temperature"] = request_body["temperature"]
    if request_body.get("top_p") is not None:
        bedrock_body["top_p"] = request_body["top_p"]

    return bedrock_body


class ProviderClient:
    """Handles HTTP communication with backend LLM providers.

    Bedrock: bedrock-runtime invoke-model (Anthropic Messages format) with SigV4.
    OpenAI: api.openai.com/v1/chat/completions with Bearer token.
    """

    def __init__(self, config: GatewayConfig, http_client: httpx.AsyncClient):
        self._config = config
        self._http_client = http_client
        self._openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self._botocore_session = BotocoreSession()

    def _get_bedrock_url(self) -> str:
        """Bedrock invoke-model endpoint with inference profile ID."""
        region = self._config.bedrock_region
        model_id = self._config.bedrock_model_id
        return (
            f"https://bedrock-runtime.{region}.amazonaws.com"
            f"/model/{model_id}/invoke"
        )

    def _sign_request(self, method: str, url: str, headers: dict, body: bytes) -> dict:
        """Sign a request with SigV4 for Bedrock."""
        credentials = self._botocore_session.get_credentials()
        if credentials is None:
            raise RuntimeError("AWS credentials not available for Bedrock signing")

        aws_request = AWSRequest(method=method, url=url, headers=headers, data=body)
        SigV4Auth(
            credentials.get_frozen_credentials(),
            "bedrock",
            self._config.bedrock_region,
        ).add_auth(aws_request)
        return dict(aws_request.headers)

    async def send_request(
        self, provider: Provider, request_body: dict
    ) -> ProviderResponse:
        """Send a chat completion request to the specified provider."""
        try:
            if provider == Provider.BEDROCK:
                return await self._send_bedrock_request(request_body)
            else:
                return await self._send_openai_request(request_body)
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

    async def _send_bedrock_request(self, request_body: dict) -> ProviderResponse:
        """Send request to Bedrock using Anthropic Messages format."""
        bedrock_body = _openai_to_bedrock_request(request_body, self._config.bedrock_model_id)
        body_bytes = json.dumps(bedrock_body).encode("utf-8")

        url = self._get_bedrock_url()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        signed_headers = self._sign_request("POST", url, headers, body_bytes)

        response = await self._http_client.post(
            url,
            content=body_bytes,
            headers=signed_headers,
            timeout=self._config.request_timeout_seconds,
        )

        if response.status_code >= 500:
            return ProviderResponse(status_code=response.status_code, body=response.json(), is_error=True)
        if response.status_code >= 400:
            return ProviderResponse(status_code=response.status_code, body=response.json(), is_error=False)

        # Translate Anthropic response to OpenAI format
        bedrock_response = response.json()
        openai_response = _bedrock_to_openai_response(bedrock_response)
        return ProviderResponse(status_code=200, body=openai_response, is_error=False)

    async def _send_openai_request(self, request_body: dict) -> ProviderResponse:
        """Send request to OpenAI directly."""
        openai_body = {**request_body, "model": self._config.openai_model}
        body_bytes = json.dumps(openai_body).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }

        response = await self._http_client.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            content=body_bytes,
            headers=headers,
            timeout=self._config.request_timeout_seconds,
        )

        is_error = response.status_code >= 500
        return ProviderResponse(status_code=response.status_code, body=response.json(), is_error=is_error)

    async def send_streaming_request(
        self, provider: Provider, request_body: dict
    ) -> AsyncGenerator[bytes, None]:
        """Send a streaming request. Only supported for OpenAI currently."""
        try:
            if provider == Provider.OPENAI:
                openai_body = {**request_body, "model": self._config.openai_model}
                body_bytes = json.dumps(openai_body).encode("utf-8")
                headers = {
                    "Authorization": f"Bearer {self._openai_api_key}",
                    "Content-Type": "application/json",
                }
                async with self._http_client.stream(
                    "POST", OPENAI_CHAT_COMPLETIONS_URL,
                    content=body_bytes, headers=headers,
                    timeout=self._config.request_timeout_seconds,
                ) as response:
                    if response.status_code >= 500:
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
            else:
                # Bedrock streaming: use invoke-model-with-response-stream
                # For simplicity, fall back to non-streaming for Bedrock
                result = await self._send_bedrock_request(request_body)
                if result.body and not result.is_error:
                    # Emit as a single SSE event
                    data = json.dumps(result.body)
                    yield f"data: {data}\n\n".encode()
                    yield b"data: [DONE]\n\n"

        except httpx.TimeoutException:
            logger.warning("Streaming timeout for provider %s", provider.value)
            return
        except httpx.ConnectError:
            logger.warning("Streaming connection error for provider %s", provider.value)
            return
