"""Tests for the configuration module."""

import os

import pytest

from gateway.config import GatewayConfig, load_config
from gateway.models import Provider


class TestGatewayConfigDefaults:
    """Test that GatewayConfig has correct default values."""

    def test_default_latency_threshold(self):
        config = GatewayConfig()
        assert config.latency_threshold_ms == 5000.0

    def test_default_error_rate_threshold(self):
        config = GatewayConfig()
        assert config.error_rate_threshold == 0.5

    def test_default_window_size(self):
        config = GatewayConfig()
        assert config.window_size == 50

    def test_default_primary_provider(self):
        config = GatewayConfig()
        assert config.primary_provider == Provider.BEDROCK

    def test_default_bedrock_model_id(self):
        config = GatewayConfig()
        assert config.bedrock_model_id == "anthropic.claude-3-sonnet-20240229-v1:0"

    def test_default_bedrock_region(self):
        config = GatewayConfig()
        assert config.bedrock_region == "us-east-1"

    def test_default_openai_model(self):
        config = GatewayConfig()
        assert config.openai_model == "gpt-4o"

    def test_default_request_timeout(self):
        config = GatewayConfig()
        assert config.request_timeout_seconds == 30.0


class TestLoadConfig:
    """Test load_config reads from environment variables."""

    def test_load_config_defaults(self, monkeypatch):
        """load_config returns defaults when no env vars are set."""
        for key in [
            "GATEWAY_LATENCY_THRESHOLD_MS",
            "GATEWAY_ERROR_RATE_THRESHOLD",
            "GATEWAY_WINDOW_SIZE",
            "GATEWAY_PRIMARY_PROVIDER",
            "GATEWAY_BEDROCK_MODEL_ID",
            "GATEWAY_BEDROCK_REGION",
            "GATEWAY_OPENAI_MODEL",
            "GATEWAY_REQUEST_TIMEOUT_SECONDS",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = load_config()
        assert config.latency_threshold_ms == 5000.0
        assert config.error_rate_threshold == 0.5
        assert config.window_size == 50
        assert config.primary_provider == Provider.BEDROCK
        assert config.bedrock_model_id == "anthropic.claude-3-sonnet-20240229-v1:0"
        assert config.bedrock_region == "us-east-1"
        assert config.openai_model == "gpt-4o"
        assert config.request_timeout_seconds == 30.0

    def test_load_config_custom_values(self, monkeypatch):
        """load_config reads custom values from environment."""
        monkeypatch.setenv("GATEWAY_LATENCY_THRESHOLD_MS", "3000")
        monkeypatch.setenv("GATEWAY_ERROR_RATE_THRESHOLD", "0.3")
        monkeypatch.setenv("GATEWAY_WINDOW_SIZE", "100")
        monkeypatch.setenv("GATEWAY_PRIMARY_PROVIDER", "openai")
        monkeypatch.setenv("GATEWAY_BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        monkeypatch.setenv("GATEWAY_BEDROCK_REGION", "eu-west-1")
        monkeypatch.setenv("GATEWAY_OPENAI_MODEL", "gpt-4-turbo")
        monkeypatch.setenv("GATEWAY_REQUEST_TIMEOUT_SECONDS", "60.0")

        config = load_config()
        assert config.latency_threshold_ms == 3000.0
        assert config.error_rate_threshold == 0.3
        assert config.window_size == 100
        assert config.primary_provider == Provider.OPENAI
        assert config.bedrock_model_id == "anthropic.claude-3-haiku-20240307-v1:0"
        assert config.bedrock_region == "eu-west-1"
        assert config.openai_model == "gpt-4-turbo"
        assert config.request_timeout_seconds == 60.0

    def test_load_config_primary_provider_case_insensitive(self, monkeypatch):
        """load_config handles uppercase provider names."""
        monkeypatch.setenv("GATEWAY_PRIMARY_PROVIDER", "OPENAI")
        config = load_config()
        assert config.primary_provider == Provider.OPENAI

    def test_load_config_invalid_provider_raises(self, monkeypatch):
        """load_config raises ValueError for invalid provider."""
        monkeypatch.setenv("GATEWAY_PRIMARY_PROVIDER", "invalid_provider")
        with pytest.raises(ValueError):
            load_config()
