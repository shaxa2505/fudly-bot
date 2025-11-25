"""
Metrics and Analytics Module for Fudly Bot.

Provides Prometheus-compatible metrics for monitoring:
- Request latency
- Request counts by handler
- Active users
- Business metrics (bookings, offers, etc.)
"""
import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """Single metric value with metadata."""

    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Counter:
    """Prometheus-style counter metric."""

    def __init__(self, name: str, description: str, labels: list[str] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: dict[tuple, float] = defaultdict(float)

    def inc(self, amount: float = 1, **labels) -> None:
        """Increment counter by amount."""
        key = self._labels_to_key(labels)
        self._values[key] += amount

    def _labels_to_key(self, labels: dict) -> tuple:
        return tuple(labels.get(name, "") for name in self.label_names)

    def get(self, **labels) -> float:
        """Get current counter value."""
        key = self._labels_to_key(labels)
        return self._values.get(key, 0)

    def collect(self) -> list[MetricValue]:
        """Collect all metric values."""
        result = []
        for key, value in self._values.items():
            labels = dict(zip(self.label_names, key))
            result.append(MetricValue(value=value, labels=labels))
        return result


class Gauge:
    """Prometheus-style gauge metric."""

    def __init__(self, name: str, description: str, labels: list[str] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: dict[tuple, float] = {}

    def set(self, value: float, **labels) -> None:
        """Set gauge to value."""
        key = self._labels_to_key(labels)
        self._values[key] = value

    def inc(self, amount: float = 1, **labels) -> None:
        """Increment gauge by amount."""
        key = self._labels_to_key(labels)
        self._values[key] = self._values.get(key, 0) + amount

    def dec(self, amount: float = 1, **labels) -> None:
        """Decrement gauge by amount."""
        key = self._labels_to_key(labels)
        self._values[key] = self._values.get(key, 0) - amount

    def _labels_to_key(self, labels: dict) -> tuple:
        return tuple(labels.get(name, "") for name in self.label_names)

    def get(self, **labels) -> float:
        """Get current gauge value."""
        key = self._labels_to_key(labels)
        return self._values.get(key, 0)

    def collect(self) -> list[MetricValue]:
        """Collect all metric values."""
        result = []
        for key, value in self._values.items():
            labels = dict(zip(self.label_names, key))
            result.append(MetricValue(value=value, labels=labels))
        return result


class Histogram:
    """Prometheus-style histogram metric."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, float("inf"))

    def __init__(
        self, name: str, description: str, labels: list[str] = None, buckets: tuple = None
    ):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: dict[tuple, dict[float, int]] = defaultdict(
            lambda: dict.fromkeys(self.buckets, 0)
        )
        self._sums: dict[tuple, float] = defaultdict(float)
        self._totals: dict[tuple, int] = defaultdict(int)

    def observe(self, value: float, **labels) -> None:
        """Observe a value."""
        key = self._labels_to_key(labels)
        self._sums[key] += value
        self._totals[key] += 1
        for bucket in self.buckets:
            if value <= bucket:
                self._counts[key][bucket] += 1

    def _labels_to_key(self, labels: dict) -> tuple:
        return tuple(labels.get(name, "") for name in self.label_names)

    def get_percentile(self, percentile: float, **labels) -> float:
        """Approximate percentile from histogram."""
        key = self._labels_to_key(labels)
        total = self._totals.get(key, 0)
        if total == 0:
            return 0

        target = total * percentile / 100
        cumulative = 0
        prev_bucket = 0

        for bucket in sorted(self.buckets):
            if bucket == float("inf"):
                continue
            cumulative = self._counts[key][bucket]
            if cumulative >= target:
                return bucket
            prev_bucket = bucket

        return prev_bucket

    def get_avg(self, **labels) -> float:
        """Get average value."""
        key = self._labels_to_key(labels)
        total = self._totals.get(key, 0)
        if total == 0:
            return 0
        return self._sums.get(key, 0) / total

    def collect(self) -> list[MetricValue]:
        """Collect all metric values (sum and count per label set)."""
        result = []
        for key in self._totals.keys():
            labels = dict(zip(self.label_names, key))
            # Export _sum
            result.append(MetricValue(value=self._sums.get(key, 0), labels={**labels, "le": "sum"}))
            # Export _count
            result.append(
                MetricValue(value=self._totals.get(key, 0), labels={**labels, "le": "count"})
            )
        return result


class MetricsRegistry:
    """Central registry for all metrics."""

    def __init__(self):
        self._metrics: dict[str, Any] = {}
        self._start_time = datetime.now(timezone.utc)

        # === System Metrics ===
        self.requests_total = self.counter(
            "fudly_requests_total", "Total number of requests", ["handler", "status"]
        )

        self.request_duration = self.histogram(
            "fudly_request_duration_seconds", "Request duration in seconds", ["handler"]
        )

        self.active_users = self.gauge(
            "fudly_active_users", "Number of active users in last hour", ["city"]
        )

        self.errors_total = self.counter(
            "fudly_errors_total", "Total number of errors", ["handler", "error_type"]
        )

        # === Business Metrics ===
        self.bookings_total = self.counter(
            "fudly_bookings_total", "Total bookings created", ["city", "status"]
        )

        self.bookings_active = self.gauge(
            "fudly_bookings_active", "Currently active bookings", ["city"]
        )

        self.offers_total = self.counter(
            "fudly_offers_total", "Total offers created", ["city", "category"]
        )

        self.offers_active = self.gauge("fudly_offers_active", "Currently active offers", ["city"])

        self.stores_total = self.gauge(
            "fudly_stores_total", "Total registered stores", ["city", "status"]
        )

        self.users_total = self.gauge(
            "fudly_users_total", "Total registered users", ["role", "city"]
        )

        self.revenue_total = self.counter(
            "fudly_revenue_total", "Total revenue from completed bookings", ["city"]
        )

        # === Performance Metrics ===
        self.db_query_duration = self.histogram(
            "fudly_db_query_duration_seconds", "Database query duration", ["query_type"]
        )

        self.cache_hits = self.counter("fudly_cache_hits_total", "Cache hit count", ["cache_type"])

        self.cache_misses = self.counter(
            "fudly_cache_misses_total", "Cache miss count", ["cache_type"]
        )

    def counter(self, name: str, description: str, labels: list[str] = None) -> Counter:
        """Create or get a counter metric."""
        if name not in self._metrics:
            self._metrics[name] = Counter(name, description, labels)
        return self._metrics[name]

    def gauge(self, name: str, description: str, labels: list[str] = None) -> Gauge:
        """Create or get a gauge metric."""
        if name not in self._metrics:
            self._metrics[name] = Gauge(name, description, labels)
        return self._metrics[name]

    def histogram(
        self, name: str, description: str, labels: list[str] = None, buckets: tuple = None
    ) -> Histogram:
        """Create or get a histogram metric."""
        if name not in self._metrics:
            self._metrics[name] = Histogram(name, description, labels, buckets)
        return self._metrics[name]

    def uptime_seconds(self) -> float:
        """Get bot uptime in seconds."""
        return (datetime.now(timezone.utc) - self._start_time).total_seconds()

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text format."""
        lines = []

        # Uptime
        lines.append("# HELP fudly_uptime_seconds Bot uptime in seconds")
        lines.append("# TYPE fudly_uptime_seconds gauge")
        lines.append(f"fudly_uptime_seconds {self.uptime_seconds():.2f}")
        lines.append("")

        for name, metric in self._metrics.items():
            lines.append(f"# HELP {name} {metric.description}")

            if isinstance(metric, Counter):
                lines.append(f"# TYPE {name} counter")
            elif isinstance(metric, Gauge):
                lines.append(f"# TYPE {name} gauge")
            elif isinstance(metric, Histogram):
                lines.append(f"# TYPE {name} histogram")

            for mv in metric.collect():
                if mv.labels:
                    label_str = ",".join(f'{k}="{v}"' for k, v in mv.labels.items())
                    lines.append(f"{name}{{{label_str}}} {mv.value}")
                else:
                    lines.append(f"{name} {mv.value}")

            lines.append("")

        return "\n".join(lines)

    def get_summary(self) -> dict[str, Any]:
        """Get human-readable metrics summary."""
        return {
            "uptime_hours": round(self.uptime_seconds() / 3600, 2),
            "total_requests": sum(v for v in self.requests_total._values.values()),
            "total_errors": sum(v for v in self.errors_total._values.values()),
            "active_bookings": sum(v for v in self.bookings_active._values.values()),
            "active_offers": sum(v for v in self.offers_active._values.values()),
            "avg_request_duration_ms": round(self.request_duration.get_avg() * 1000, 2),
            "p95_request_duration_ms": round(self.request_duration.get_percentile(95) * 1000, 2),
        }


# Global metrics instance
metrics = MetricsRegistry()


def track_request(handler_name: str):
    """Decorator to track request metrics."""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                metrics.errors_total.inc(handler=handler_name, error_type=type(e).__name__)
                raise
            finally:
                duration = time.time() - start_time
                metrics.requests_total.inc(handler=handler_name, status=status)
                metrics.request_duration.observe(duration, handler=handler_name)

        return wrapper

    return decorator


def track_db_query(query_type: str):
    """Decorator to track database query metrics."""

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                metrics.db_query_duration.observe(duration, query_type=query_type)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                metrics.db_query_duration.observe(duration, query_type=query_type)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Business metrics helpers
def track_booking_created(city: str, status: str = "pending"):
    """Track new booking creation."""
    metrics.bookings_total.inc(city=city, status=status)
    metrics.bookings_active.inc(city=city)


def track_booking_completed(city: str, amount: float = 0):
    """Track booking completion."""
    metrics.bookings_active.dec(city=city)
    metrics.bookings_total.inc(city=city, status="completed")
    if amount > 0:
        metrics.revenue_total.inc(amount, city=city)


def track_booking_cancelled(city: str):
    """Track booking cancellation."""
    metrics.bookings_active.dec(city=city)
    metrics.bookings_total.inc(city=city, status="cancelled")


def track_offer_created(city: str, category: str = "food"):
    """Track new offer creation."""
    metrics.offers_total.inc(city=city, category=category)
    metrics.offers_active.inc(city=city)


def track_offer_sold_out(city: str):
    """Track offer sold out."""
    metrics.offers_active.dec(city=city)


def track_cache_hit(cache_type: str = "default"):
    """Track cache hit."""
    metrics.cache_hits.inc(cache_type=cache_type)


def track_cache_miss(cache_type: str = "default"):
    """Track cache miss."""
    metrics.cache_misses.inc(cache_type=cache_type)


async def update_business_metrics(db) -> None:
    """Update business metrics from database (call periodically)."""
    try:
        # Update active offers count
        # This would query the database for current counts
        # Example (implement based on your DB structure):
        # offers = db.get_active_offers_count_by_city()
        # for city, count in offers.items():
        #     metrics.offers_active.set(count, city=city)
        pass
    except Exception as e:
        logger.error(f"Failed to update business metrics: {e}")
