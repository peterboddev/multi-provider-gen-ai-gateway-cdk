"""Configuration module.

Loads gateway configuration from environment variables.
Defines GatewayConfig dataclass with sensible defaults.
"""

import os
from dataclasses import dataclass

from gateway.models import Provider


@dataclass
class GatewayConfig:
    """Gateway configuration loaded from environment variables."""

    latency_threshold_ms: float = 5000.0
    error_rate_threshold: float = 0.5
    window_size: int = 50
    primary_provider: Provider = Provider.BEDROCK
    bedrock_model_id: str = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_region: str = "us-east-1"
    openai_model: str = "gpt-4o"
    request_timeout_seconds: float = 30.0


def load_config() -> GatewayConfig:
    """Load gateway configuration from environment variables.

    Reads GATEWAY_* environment variables and returns a GatewayConfig
    instance with values from the environment or defaults.
    """
    primary_provider_str = os.environ.get("GATEWAY_PRIMARY_PROVIDER", "bedrock").lower()
    primary_provider = Provider(primary_provider_str)

    return GatewayConfig(
        latency_threshold_ms=float(
            os.environ.get("GATEWAY_LATENCY_THRESHOLD_MS", "5000")
        ),
        error_rate_threshold=float(
            os.environ.get("GATEWAY_ERROR_RATE_THRESHOLD", "0.5")
        ),
        window_size=int(os.environ.get("GATEWAY_WINDOW_SIZE", "50")),
        primary_provider=primary_provider,
        bedrock_model_id=os.environ.get(
            "GATEWAY_BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
        ),
        bedrock_region=os.environ.get("GATEWAY_BEDROCK_REGION", "us-east-1"),
        openai_model=os.environ.get("GATEWAY_OPENAI_MODEL", "gpt-4o"),
        request_timeout_seconds=float(
            os.environ.get("GATEWAY_REQUEST_TIMEOUT_SECONDS", "30.0")
        ),
    )
