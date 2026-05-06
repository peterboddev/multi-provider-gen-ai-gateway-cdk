"""Routing Engine module.

Selects the best provider for each request based on health metrics.
Implements latency-based routing with automatic failover.
"""

from gateway.config import GatewayConfig
from gateway.health import HealthTracker
from gateway.models import Provider


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

        # Case: one healthy, one unhealthy
        if primary_healthy and not secondary_healthy:
            return primary
        if secondary_healthy and not primary_healthy:
            return secondary

        # Case: both healthy - pick lower score, primary wins ties
        if primary_healthy and secondary_healthy:
            primary_score = self._compute_health_score(primary)
            secondary_score = self._compute_health_score(secondary)
            if primary_score <= secondary_score:
                return primary
            return secondary

        # Case: both unhealthy - pick lower error rate, primary wins ties
        primary_error_rate = self._health_tracker.get_error_rate(primary)
        secondary_error_rate = self._health_tracker.get_error_rate(secondary)
        if primary_error_rate <= secondary_error_rate:
            return primary
        return secondary

    def get_fallback_provider(self, failed_provider: Provider) -> Provider:
        """Return the alternate provider for retry."""
        return self._get_alternate(failed_provider)

    def _get_alternate(self, provider: Provider) -> Provider:
        """Return the other provider."""
        if provider == Provider.BEDROCK:
            return Provider.OPENAI
        return Provider.BEDROCK
