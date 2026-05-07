"""Main FastAPI application entry point.

Registers routes and initializes the routing engine and health tracker on startup.

Routes:
- POST /v1/chat/completions — main proxy endpoint
- GET /health — health check endpoint
"""

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from gateway.config import GatewayConfig, load_config
from gateway.health import HealthTracker
from gateway.logging_config import configure_logging
from gateway.metrics import emit_request_metrics
from gateway.models import (
    ChatCompletionRequest,
    ErrorResponse,
    ErrorDetail,
    Provider,
)
from gateway.providers import ProviderClient
from gateway.routing import RoutingEngine

logger = logging.getLogger(__name__)

# Module-level references set during lifespan
_config: GatewayConfig | None = None
_health_tracker: HealthTracker | None = None
_provider_client: ProviderClient | None = None
_routing_engine: RoutingEngine | None = None
_http_client: httpx.AsyncClient | None = None
_gateway_api_key: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize components on startup and clean up on shutdown."""
    global _config, _health_tracker, _provider_client, _routing_engine, _http_client, _gateway_api_key

    configure_logging()

    _config = load_config()
    _gateway_api_key = os.environ.get("GATEWAY_API_KEY", "")
    _health_tracker = HealthTracker(window_size=_config.window_size)
    _http_client = httpx.AsyncClient(timeout=_config.request_timeout_seconds)
    _provider_client = ProviderClient(config=_config, http_client=_http_client)
    _routing_engine = RoutingEngine(health_tracker=_health_tracker, config=_config)

    yield

    await _http_client.aclose()


app = FastAPI(
    title="Multi-Provider Gen AI Gateway",
    description="OpenAI-compatible API gateway with latency-based routing and automatic failover",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def authenticate(request: Request, call_next):
    """Validate API key on all endpoints except /health."""
    if request.url.path == "/health":
        return await call_next(request)

    # Skip auth if no key is configured (open mode)
    if not _gateway_api_key:
        return await call_next(request)

    # Check Authorization: Bearer <key> or X-API-Key header
    auth_header = request.headers.get("authorization", "")
    api_key_header = request.headers.get("x-api-key", "")

    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif api_key_header:
        token = api_key_header

    if token != _gateway_api_key:
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "Invalid API key", "type": "authentication_error"}},
        )

    return await call_next(request)


def _emit_request_log(
    provider: str,
    latency_ms: float,
    status_code: int,
    stream: bool = False,
    fallback: bool = False,
    fallback_reason: str | None = None,
) -> None:
    """Emit a structured JSON log entry for a completed request."""
    log_entry = {
        "provider": provider,
        "latency_ms": round(latency_ms, 2),
        "status_code": status_code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stream": stream,
    }
    if fallback:
        log_entry["fallback"] = True
        if fallback_reason:
            log_entry["fallback_reason"] = fallback_reason
    logger.info(json.dumps(log_entry))

    # Emit EMF metrics
    emit_request_metrics(
        provider=provider,
        latency_ms=latency_ms,
        status_code=status_code,
        is_fallback=fallback,
    )


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns provider health status with overall system health.
    - 200 if at least one provider is healthy ("healthy" or "degraded")
    - 503 if no providers are healthy ("unhealthy")
    """
    providers_status = {}
    for provider in Provider:
        providers_status[provider.value] = {
            "healthy": _health_tracker.is_healthy(provider, _config),
            "avg_latency_ms": round(_health_tracker.get_avg_latency(provider), 1),
            "error_rate": round(_health_tracker.get_error_rate(provider), 4),
        }

    healthy_count = sum(
        1 for p in providers_status.values() if p["healthy"]
    )

    if healthy_count == len(providers_status):
        status = "healthy"
    elif healthy_count > 0:
        status = "degraded"
    else:
        status = "unhealthy"

    response_body = {
        "status": status,
        "providers": providers_status,
    }

    status_code = 200 if status != "unhealthy" else 503
    return JSONResponse(status_code=status_code, content=response_body)


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Handle chat completion requests with routing and failover.

    Selects the healthiest provider, sends the request, and retries
    with the fallback provider on 5xx/timeout failures. 4xx errors
    are passed through without retry.
    """
    request_body = request.model_dump(exclude_none=True)

    # Streaming path
    if request.stream:
        return await _handle_streaming_request(request_body)

    # Non-streaming path
    return await _handle_sync_request(request_body)


async def _handle_sync_request(request_body: dict) -> JSONResponse:
    """Handle a synchronous (non-streaming) chat completion request."""
    provider = _routing_engine.select_provider()
    start_time = time.time()

    response = await _provider_client.send_request(provider, request_body)
    latency_ms = (time.time() - start_time) * 1000

    # 4xx: pass through without retry or health recording
    if 400 <= response.status_code < 500:
        _emit_request_log(
            provider=provider.value,
            latency_ms=latency_ms,
            status_code=response.status_code,
        )
        return JSONResponse(status_code=response.status_code, content=response.body)

    # 5xx or connectivity error: record failure and try fallback
    if response.is_error:
        _health_tracker.record_failure(provider)
        fallback_provider = _routing_engine.get_fallback_provider(provider)

        fallback_start = time.time()
        fallback_response = await _provider_client.send_request(
            fallback_provider, request_body
        )
        fallback_latency_ms = (time.time() - fallback_start) * 1000

        # 4xx from fallback: pass through
        if 400 <= fallback_response.status_code < 500:
            _emit_request_log(
                provider=fallback_provider.value,
                latency_ms=fallback_latency_ms,
                status_code=fallback_response.status_code,
                fallback=True,
                fallback_reason="primary_provider_failure",
            )
            return JSONResponse(
                status_code=fallback_response.status_code,
                content=fallback_response.body,
            )

        # Fallback also failed
        if fallback_response.is_error:
            _health_tracker.record_failure(fallback_provider)
            total_latency = latency_ms + fallback_latency_ms
            _emit_request_log(
                provider=fallback_provider.value,
                latency_ms=total_latency,
                status_code=502,
                fallback=True,
                fallback_reason="primary_provider_failure",
            )
            error = ErrorResponse(
                error=ErrorDetail(
                    message="All providers unavailable",
                    type="server_error",
                )
            )
            return JSONResponse(status_code=502, content=error.model_dump())

        # Fallback succeeded
        _health_tracker.record_success(fallback_provider, fallback_latency_ms)
        _emit_request_log(
            provider=fallback_provider.value,
            latency_ms=fallback_latency_ms,
            status_code=fallback_response.status_code,
            fallback=True,
            fallback_reason="primary_provider_failure",
        )
        return JSONResponse(
            status_code=fallback_response.status_code,
            content=fallback_response.body,
        )

    # Success on primary provider
    _health_tracker.record_success(provider, latency_ms)
    _emit_request_log(
        provider=provider.value,
        latency_ms=latency_ms,
        status_code=response.status_code,
    )
    return JSONResponse(status_code=response.status_code, content=response.body)


async def _handle_streaming_request(request_body: dict) -> StreamingResponse:
    """Handle a streaming (SSE) chat completion request."""
    provider = _routing_engine.select_provider()

    async def generate_stream():
        """Yield SSE chunks from the selected provider, with fallback."""
        nonlocal provider
        start_time = time.time()
        chunk_received = False

        async for chunk in _provider_client.send_streaming_request(
            provider, request_body
        ):
            chunk_received = True
            yield chunk

        latency_ms = (time.time() - start_time) * 1000

        if chunk_received:
            _health_tracker.record_success(provider, latency_ms)
            _emit_request_log(
                provider=provider.value,
                latency_ms=latency_ms,
                status_code=200,
                stream=True,
            )
            return

        # No chunks received — streaming failed, try fallback
        _health_tracker.record_failure(provider)
        fallback_provider = _routing_engine.get_fallback_provider(provider)
        fallback_start = time.time()
        fallback_chunk_received = False

        async for chunk in _provider_client.send_streaming_request(
            fallback_provider, request_body
        ):
            fallback_chunk_received = True
            yield chunk

        fallback_latency_ms = (time.time() - fallback_start) * 1000

        if fallback_chunk_received:
            _health_tracker.record_success(fallback_provider, fallback_latency_ms)
            _emit_request_log(
                provider=fallback_provider.value,
                latency_ms=fallback_latency_ms,
                status_code=200,
                stream=True,
                fallback=True,
                fallback_reason="primary_provider_failure",
            )
        else:
            _health_tracker.record_failure(fallback_provider)
            _emit_request_log(
                provider=fallback_provider.value,
                latency_ms=fallback_latency_ms,
                status_code=502,
                stream=True,
                fallback=True,
                fallback_reason="primary_provider_failure",
            )
            # Yield an SSE error event
            error_data = json.dumps(
                {"error": {"message": "All providers unavailable", "type": "server_error"}}
            )
            yield f"data: {error_data}\n\n".encode()

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
