"""Tests for metrics module."""
import pytest

from app.core.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    metrics,
    track_booking_created,
    track_cache_hit,
    track_cache_miss,
    track_request,
)


class TestCounter:
    """Tests for Counter metric."""

    def test_counter_increment(self):
        counter = Counter("test_counter", "Test counter", ["label1"])
        counter.inc(label1="value1")
        assert counter.get(label1="value1") == 1
        counter.inc(2, label1="value1")
        assert counter.get(label1="value1") == 3

    def test_counter_different_labels(self):
        counter = Counter("test_counter", "Test counter", ["label1"])
        counter.inc(label1="a")
        counter.inc(label1="b")
        counter.inc(label1="a")
        assert counter.get(label1="a") == 2
        assert counter.get(label1="b") == 1

    def test_counter_collect(self):
        counter = Counter("test_counter", "Test counter", ["type"])
        counter.inc(type="error")
        counter.inc(type="success")
        counter.inc(type="success")

        values = counter.collect()
        assert len(values) == 2


class TestGauge:
    """Tests for Gauge metric."""

    def test_gauge_set(self):
        gauge = Gauge("test_gauge", "Test gauge")
        gauge.set(42)
        assert gauge.get() == 42
        gauge.set(100)
        assert gauge.get() == 100

    def test_gauge_inc_dec(self):
        gauge = Gauge("test_gauge", "Test gauge", ["city"])
        gauge.set(10, city="Tashkent")
        gauge.inc(5, city="Tashkent")
        assert gauge.get(city="Tashkent") == 15
        gauge.dec(3, city="Tashkent")
        assert gauge.get(city="Tashkent") == 12


class TestHistogram:
    """Tests for Histogram metric."""

    def test_histogram_observe(self):
        histogram = Histogram("test_hist", "Test histogram", ["handler"])
        histogram.observe(0.1, handler="test")
        histogram.observe(0.2, handler="test")
        histogram.observe(0.5, handler="test")

        avg = histogram.get_avg(handler="test")
        assert 0.26 < avg < 0.28  # ~0.267

    def test_histogram_percentile(self):
        histogram = Histogram("test_hist", "Test histogram")
        # Add values that fall into different buckets
        for _ in range(100):
            histogram.observe(0.05)  # <= 0.05 bucket
        for _ in range(100):
            histogram.observe(0.5)  # <= 0.5 bucket

        p50 = histogram.get_percentile(50)
        assert p50 <= 0.5


class TestMetricsRegistry:
    """Tests for MetricsRegistry."""

    def test_registry_creates_metrics(self):
        registry = MetricsRegistry()
        assert registry.requests_total is not None
        assert registry.request_duration is not None
        assert registry.active_users is not None

    def test_registry_uptime(self):
        registry = MetricsRegistry()
        uptime = registry.uptime_seconds()
        assert uptime >= 0

    def test_registry_export_prometheus(self):
        registry = MetricsRegistry()
        registry.requests_total.inc(handler="test", status="success")

        output = registry.export_prometheus()
        assert "fudly_uptime_seconds" in output
        assert "fudly_requests_total" in output

    def test_registry_get_summary(self):
        registry = MetricsRegistry()
        registry.requests_total.inc(handler="test", status="success")

        summary = registry.get_summary()
        assert "uptime_hours" in summary
        assert "total_requests" in summary
        assert summary["total_requests"] >= 1


class TestBusinessMetrics:
    """Tests for business metrics helpers."""

    def test_track_booking_created(self):
        initial = metrics.bookings_total.get(city="Test", status="pending")
        track_booking_created("Test")
        after = metrics.bookings_total.get(city="Test", status="pending")
        assert after == initial + 1

    def test_track_cache_operations(self):
        hits_before = metrics.cache_hits.get(cache_type="test")
        misses_before = metrics.cache_misses.get(cache_type="test")

        track_cache_hit("test")
        track_cache_miss("test")

        assert metrics.cache_hits.get(cache_type="test") == hits_before + 1
        assert metrics.cache_misses.get(cache_type="test") == misses_before + 1


class TestDecorators:
    """Tests for metric decorators."""

    @pytest.mark.asyncio
    async def test_track_request_decorator(self):
        @track_request("test_handler")
        async def sample_handler():
            return "ok"

        result = await sample_handler()
        assert result == "ok"

        # Check that metric was recorded
        assert metrics.requests_total.get(handler="test_handler", status="success") >= 1

    @pytest.mark.asyncio
    async def test_track_request_error(self):
        @track_request("error_handler")
        async def failing_handler():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            await failing_handler()

        # Check error was tracked
        assert metrics.errors_total.get(handler="error_handler", error_type="ValueError") >= 1
        assert metrics.requests_total.get(handler="error_handler", status="error") >= 1
