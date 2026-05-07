"""Routing Engine module.

Selects the best provider for each request based on health metrics.
Implements latency-based routing with automatic failover.
"""

import json
import logging

from gateway.config import GatewayConfig
from gateway.health import HealthTracker
from gateway.metrics import emit_routing_decision
from gateway.models import Provider

logger = logging.getLogger(__name__)


class RoutingEngine:
    """Selects the healthiest provider for each request.

    Uses a health score formula: avg_latency_ms * (1 + error_rate)
    to rank providers. Supports automatic failover when a provider
    becomes unhealthy.
    """

    def __init__(self, health_tracker: HealthTracker, config: GatewayConfig):
        self._health_tracker = health_tracker
        self._config = config

    def _compute_health_score(self, provider: Provider) -> float:
        """Compute health score for a provider.

        Score = avg_latency_ms * (1 + error_rate)
        Lower score indicates a healthier provider.
        """
        avg_latency = self._health_tracker.get_avg_latency(provider)
        error_rate = self._health_tracker.get_error_rate(provider)
        return avg_latency * (1 + error_rate)

    def select_provider(self) -> Provider:
        """Select the healthiest provider based on latency and error rate.

        Algorithm:
        1. If one provider is healthy and the other unhealthy, select the healthy one.
        2. If both are healthy, select the one with the lower health score
           (primary wins ties).
        3. If both are unhealthy, select the one with the lower error rate
           (primary wins ties).
        """
        primary = self._config.primary_provider
        secondary = self._get_alternate(primary)

        primary_healthy = self._health_tracker.is_healthy(primary, self._config)
        secondary_healthy = self._health_tracker.is_healthy(secondary, self._config)

        primary_score = self._compute_health_score(primary)
        secondary_score = self._compute_health_score(secondary)
        primary_error_rate = self._health_tracker.get_error_rate(primary)
        secondary_error_rate = self._health_tracker.get_error_rate(secondary)

        # Case: one healthy, one unhealthy
        if primary_healthy and not secondary_healthy:
            selected = primary
            reason = "secondary_unhealthy"
        elif secondary_healthy and not primary_healthy:
            selected = secondary
            reason = "primary_unhealthy"
        # Case: both healthy - pick lower score, primary wins ties
        elif primary_healthy and secondary_healthy:
            if primary_score <= secondary_score:
                selected = primary
                reason = "lower_score_or_primary_tie"
            else:
                selected = secondary
                reason = "lower_score"
        # Case: both unhealthy - pick lower error rate, primary wins ties
        else:
            if primary_error_rate <= secondary_error_rate:
                selected = primary
                reason = "lower_error_rate_or_primary_tie"
            else:
                selected = secondary
                reason = "lower_error_rate"

        # Emit EMF metrics for CloudWatch dashboard
        bedrock_latency = self._health_tracker.get_avg_latency(Provider.BEDROCK)
        openai_latency = self._health_tracker.get_avg_latency(Provider.OPENAI)
        bedrock_err = self._health_tracker.get_error_rate(Provider.BEDROCK)
        openai_err = self._health_tracker.get_error_rate(Provider.OPENAI)
        bedrock_sc = self._compute_health_score(Provider.BEDROCK)
        openai_sc = self._compute_health_score(Provider.OPENAI)
        bedrock_h = self._health_tracker.is_healthy(Provider.BEDROCK, self._config)
        openai_h = self._health_tracker.is_healthy(Provider.OPENAI, self._config)

        emit_routing_decision(
            selected=selected.value,
            reason=reason,
            bedrock_score=bedrock_sc,
            openai_score=openai_sc,
            bedrock_healthy=bedrock_h,
            openai_healthy=openai_h,
            bedrock_error_rate=bedrock_err,
            openai_error_rate=openai_err,
            bedrock_avg_latency_ms=bedrock_latency,
            openai_avg_latency_ms=openai_latency,
        )

        # Structured log for CloudWatch Logs Insights
        logger.info(json.dumps({
            "event": "routing_decision",
            "selected": selected.value,
            "reason": reason,
            "bedrock_score": round(bedrock_sc, 2),
            "openai_score": round(openai_sc, 2),
            "bedrock_healthy": bedrock_h,
            "openai_healthy": openai_h,
            "bedrock_error_rate": round(bedrock_err, 4),
            "openai_error_rate": round(openai_err, 4),
            "bedrock_avg_latency_ms": round(bedrock_latency, 2),
            "openai_avg_latency_ms": round(openai_latency, 2),
        }))

        return selected

    def get_fallback_provider(self, failed_provider: Provider) -> Provider:
        """Return the alternate provider for retry."""
        return self._get_alternate(failed_provider)

    def _get_alternate(self, provider: Provider) -> Provider:
        """Return the other provider."""
        if provider == Provider.BEDROCK:
            return Provider.OPENAI
        return Provider.BEDROCK
