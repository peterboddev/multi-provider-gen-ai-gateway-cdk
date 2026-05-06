"""Unit tests for the RoutingEngine module."""

from gateway.config import GatewayConfig
from gateway.health import HealthTracker
from gateway.models import Provider
from gateway.routing import RoutingEngine


class TestRoutingEngineSelectProvider:
    """Tests for RoutingEngine.select_provider()."""

    def test_both_healthy_no_data_selects_primary(self):
        """With no health data, both providers are healthy; primary wins."""
        config = GatewayConfig(primary_provider=Provider.BEDROCK)
        tracker = HealthTracker(window_size=10)
        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.BEDROCK

    def test_both_healthy_primary_lower_score(self):
        """Both healthy, primary has lower score -> select primary."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=5000.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: latency=100, error_rate=0 -> score=100
        tracker.record_success(Provider.BEDROCK, 100.0)
        # Secondary: latency=200, error_rate=0 -> score=200
        tracker.record_success(Provider.OPENAI, 200.0)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.BEDROCK

    def test_both_healthy_secondary_lower_score(self):
        """Both healthy, secondary has lower score -> select secondary."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=5000.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: latency=300, error_rate=0 -> score=300
        tracker.record_success(Provider.BEDROCK, 300.0)
        # Secondary: latency=100, error_rate=0 -> score=100
        tracker.record_success(Provider.OPENAI, 100.0)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.OPENAI

    def test_both_healthy_equal_score_selects_primary(self):
        """Both healthy with equal scores -> primary wins tie."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=5000.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        # Both have same latency and error rate
        tracker.record_success(Provider.BEDROCK, 100.0)
        tracker.record_success(Provider.OPENAI, 100.0)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.BEDROCK

    def test_primary_healthy_secondary_unhealthy(self):
        """Primary healthy, secondary unhealthy -> select primary."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=500.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: healthy
        tracker.record_success(Provider.BEDROCK, 100.0)
        # Secondary: unhealthy (high latency)
        tracker.record_success(Provider.OPENAI, 600.0)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.BEDROCK

    def test_secondary_healthy_primary_unhealthy(self):
        """Primary unhealthy, secondary healthy -> select secondary."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=500.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: unhealthy (high latency)
        tracker.record_success(Provider.BEDROCK, 600.0)
        # Secondary: healthy
        tracker.record_success(Provider.OPENAI, 100.0)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.OPENAI

    def test_primary_unhealthy_high_error_rate(self):
        """Primary unhealthy due to error rate, secondary healthy -> select secondary."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=5000.0,
            error_rate_threshold=0.3,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: high error rate (4 failures out of 5 = 0.8)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_success(Provider.BEDROCK, 100.0)
        # Secondary: healthy
        tracker.record_success(Provider.OPENAI, 200.0)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.OPENAI

    def test_both_unhealthy_primary_lower_error_rate(self):
        """Both unhealthy, primary has lower error rate -> select primary."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=500.0,
            error_rate_threshold=0.3,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: unhealthy, error_rate = 0.5
        tracker.record_success(Provider.BEDROCK, 600.0)
        tracker.record_failure(Provider.BEDROCK)
        # Secondary: unhealthy, error_rate = 0.75
        tracker.record_success(Provider.OPENAI, 600.0)
        tracker.record_failure(Provider.OPENAI)
        tracker.record_failure(Provider.OPENAI)
        tracker.record_failure(Provider.OPENAI)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.BEDROCK

    def test_both_unhealthy_secondary_lower_error_rate(self):
        """Both unhealthy, secondary has lower error rate -> select secondary."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=500.0,
            error_rate_threshold=0.3,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: unhealthy, error_rate = 0.75
        tracker.record_success(Provider.BEDROCK, 600.0)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        # Secondary: unhealthy, error_rate = 0.5
        tracker.record_success(Provider.OPENAI, 600.0)
        tracker.record_failure(Provider.OPENAI)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.OPENAI

    def test_both_unhealthy_equal_error_rate_selects_primary(self):
        """Both unhealthy with equal error rates -> primary wins tie."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=500.0,
            error_rate_threshold=0.3,
        )
        tracker = HealthTracker(window_size=10)
        # Both: unhealthy, same error_rate = 0.5
        tracker.record_success(Provider.BEDROCK, 600.0)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_success(Provider.OPENAI, 600.0)
        tracker.record_failure(Provider.OPENAI)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.BEDROCK

    def test_openai_as_primary_provider(self):
        """When OpenAI is configured as primary, it wins ties."""
        config = GatewayConfig(
            primary_provider=Provider.OPENAI,
            latency_threshold_ms=5000.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        tracker.record_success(Provider.BEDROCK, 100.0)
        tracker.record_success(Provider.OPENAI, 100.0)

        engine = RoutingEngine(tracker, config)
        assert engine.select_provider() == Provider.OPENAI

    def test_health_score_formula(self):
        """Verify health score formula: avg_latency * (1 + error_rate)."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=5000.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: latency=200, error_rate=0.2 -> score=200*(1+0.2)=240
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_failure(Provider.BEDROCK)
        # Secondary: latency=300, error_rate=0 -> score=300*(1+0)=300
        tracker.record_success(Provider.OPENAI, 300.0)

        engine = RoutingEngine(tracker, config)
        # Primary score (240) < secondary score (300), select primary
        assert engine.select_provider() == Provider.BEDROCK

    def test_health_score_secondary_wins_with_lower_combined(self):
        """Secondary wins when its combined score is lower despite higher latency."""
        config = GatewayConfig(
            primary_provider=Provider.BEDROCK,
            latency_threshold_ms=5000.0,
            error_rate_threshold=0.5,
        )
        tracker = HealthTracker(window_size=10)
        # Primary: latency=200, error_rate=0.4 -> score=200*(1+0.4)=280
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_success(Provider.BEDROCK, 200.0)
        tracker.record_failure(Provider.BEDROCK)
        tracker.record_failure(Provider.BEDROCK)
        # Secondary: latency=250, error_rate=0 -> score=250*(1+0)=250
        tracker.record_success(Provider.OPENAI, 250.0)

        engine = RoutingEngine(tracker, config)
        # Secondary score (250) < primary score (280), select secondary
        assert engine.select_provider() == Provider.OPENAI


class TestRoutingEngineGetFallback:
    """Tests for RoutingEngine.get_fallback_provider()."""

    def test_fallback_from_bedrock(self):
        """Fallback from Bedrock returns OpenAI."""
        config = GatewayConfig()
        tracker = HealthTracker(window_size=10)
        engine = RoutingEngine(tracker, config)
        assert engine.get_fallback_provider(Provider.BEDROCK) == Provider.OPENAI

    def test_fallback_from_openai(self):
        """Fallback from OpenAI returns Bedrock."""
        config = GatewayConfig()
        tracker = HealthTracker(window_size=10)
        engine = RoutingEngine(tracker, config)
        assert engine.get_fallback_provider(Provider.OPENAI) == Provider.BEDROCK
