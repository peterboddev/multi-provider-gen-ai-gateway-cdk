"""Health Tracker module.

Maintains a sliding window of request outcomes per provider.
Tracks latency and error rate metrics for routing decisions.
"""

import time
from collections import deque
from dataclasses import dataclass

from gateway.config import GatewayConfig
from gateway.models import Provider


@dataclass
class HealthEntry:
    """A single health observation for a provider request."""

    success: bool
    latency_ms: float | None  # None for failures (timeout/connection error)
    timestamp: float  # time.time()


class HealthTracker:
    """Tracks provider health using a sliding window of request outcomes.

    Maintains a deque per provider with a configurable maximum window size.
    Provides rolling average latency and error rate calculations for
    routing decisions.
    """

    def __init__(self, window_size: int = 50):
        self._window_size = window_size
        self._windows: dict[Provider, deque[HealthEntry]] = {}

    def _get_window(self, provider: Provider) -> deque[HealthEntry]:
        """Get or create the sliding window for a provider."""
        if provider not in self._windows:
            self._windows[provider] = deque(maxlen=self._window_size)
        return self._windows[provider]

    def record_success(self, provider: Provider, latency_ms: float) -> None:
        """Record a successful request with its latency."""
        window = self._get_window(provider)
        window.append(
            HealthEntry(success=True, latency_ms=latency_ms, timestamp=time.time())
        )

    def record_failure(self, provider: Provider) -> None:
        """Record a failed request."""
        window = self._get_window(provider)
        window.append(
            HealthEntry(success=False, latency_ms=None, timestamp=time.time())
        )

    def get_avg_latency(self, provider: Provider) -> float:
        """Get rolling average latency for a provider.

        Only considers successful requests for the calculation.
        Returns 0.0 if no successful entries exist.
        """
        window = self._get_window(provider)
        successful_latencies = [
            entry.latency_ms for entry in window if entry.success and entry.latency_ms is not None
        ]
        if not successful_latencies:
            return 0.0
        return sum(successful_latencies) / len(successful_latencies)

    def get_error_rate(self, provider: Provider) -> float:
        """Get rolling error rate (0.0 to 1.0) for a provider.

        Error rate = count of failures / total entries in window.
        Returns 0.0 if no entries exist.
        """
        window = self._get_window(provider)
        if not window:
            return 0.0
        failures = sum(1 for entry in window if not entry.success)
        return failures / len(window)

    def is_healthy(self, provider: Provider, config: GatewayConfig) -> bool:
        """Check if provider is within configured thresholds.

        A provider is healthy if:
        - avg_latency < latency_threshold_ms AND error_rate < error_rate_threshold
        - If the window is empty, the provider is considered healthy (no data = assume healthy)
        """
        window = self._get_window(provider)
        if not window:
            return True
        avg_latency = self.get_avg_latency(provider)
        error_rate = self.get_error_rate(provider)
        return (
            avg_latency < config.latency_threshold_ms
            and error_rate < config.error_rate_threshold
        )
