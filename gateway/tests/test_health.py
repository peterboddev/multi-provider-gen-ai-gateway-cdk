"""Unit tests for the HealthTracker module."""

from gateway.config import GatewayConfig
from gateway.health import HealthEntry, HealthTracker
from gateway.models import Provider


class TestHealthEntry:
    """Tests for the HealthEntry dataclass."""

    def test_success_entry(self):
        entry = HealthEntry(success=True, latency_ms=150.0, timestamp=1000.0)
        assert entry.success is True
        assert entry.latency_ms == 150.0
        assert entry.timestamp == 1000.0

    def test_failure_entry(self):
        entry = HealthEntry(success=False, latency_ms=None, timestamp=1000.0)
        assert entry.success is False
        assert entry.latency_ms is None


class TestHealthTracker:
    """Tests for the HealthTracker class."""

    def test_record_success(self):
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.BEDROCK, 100.0)
        assert tracker.get_avg_latency(Provider.BEDROCK) == 100.0
        assert tracker.get_error_rate(Provider.BEDROCK) == 0.0

    def test_record_failure(self):
        tracker = HealthTracker(window_size=10)
        tracker.record_failure(Provider.BEDROCK)
        assert tracker.get_error_rate(Provider.BEDROCK) == 1.0

    def test_avg_latency_only_considers_successes(self):
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.OPENAI, 100.0)
        tracker.record_success(Provider.OPENAI, 200.0)
        tracker.record_failure(Provider.OPENAI)
        assert tracker.get_avg_latency(Provider.OPENAI) == 150.0

    def test_avg_latency_empty_window(self):
        tracker = HealthTracker(window_size=10)
        assert tracker.get_avg_latency(Provider.BEDROCK) == 0.0

    def test_avg_latency_all_failures(self):
        tracker = HealthTracker(window_size=10)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        assert tracker.get_avg_latency(Provider.BEDROCK) == 0.0

    def test_error_rate_empty_window(self):
        tracker = HealthTracker(window_size=10)
        assert tracker.get_error_rate(Provider.BEDROCK) == 0.0

    def test_error_rate_mixed(self):
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.BEDROCK, 100.0)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_failure(Provider.BEDROCK)
        assert tracker.get_error_rate(Provider.BEDROCK) == 0.5

    def test_sliding_window_evicts_old_entries(self):
        tracker = HealthTracker(window_size=3)
        tracker.record_success(Provider.BEDROCK, 100.0)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_success(Provider.BEDROCK, 300.0)
        # This should evict the first entry (100.0)
        tracker.record_success(Provider.BEDROCK, 400.0)
        assert tracker.get_avg_latency(Provider.BEDROCK) == 300.0  # (200+300+400)/3

    def test_is_healthy_empty_window(self):
        tracker = HealthTracker(window_size=10)
        config = GatewayConfig()
        assert tracker.is_healthy(Provider.BEDROCK, config) is True

    def test_is_healthy_below_thresholds(self):
        tracker = HealthTracker(window_size=10)
        config = GatewayConfig(latency_threshold_ms=5000.0, error_rate_threshold=0.5)
        tracker.record_success(Provider.BEDROCK, 100.0)
        tracker.record_success(Provider.BEDROCK, 200.0)
        assert tracker.is_healthy(Provider.BEDROCK, config) is True

    def test_is_unhealthy_high_latency(self):
        tracker = HealthTracker(window_size=10)
        config = GatewayConfig(latency_threshold_ms=500.0, error_rate_threshold=0.5)
        tracker.record_success(Provider.BEDROCK, 600.0)
        tracker.record_success(Provider.BEDROCK, 700.0)
        assert tracker.is_healthy(Provider.BEDROCK, config) is False

    def test_is_unhealthy_high_error_rate(self):
        tracker = HealthTracker(window_size=10)
        config = GatewayConfig(latency_threshold_ms=5000.0, error_rate_threshold=0.3)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_success(Provider.BEDROCK, 100.0)
        # error_rate = 2/3 ≈ 0.667 > 0.3
        assert tracker.is_healthy(Provider.BEDROCK, config) is False

    def test_providers_tracked_independently(self):
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.BEDROCK, 100.0)
        tracker.record_failure(Provider.OPENAI)
        assert tracker.get_avg_latency(Provider.BEDROCK) == 100.0
        assert tracker.get_error_rate(Provider.BEDROCK) == 0.0
        assert tracker.get_avg_latency(Provider.OPENAI) == 0.0
        assert tracker.get_error_rate(Provider.OPENAI) == 1.0
