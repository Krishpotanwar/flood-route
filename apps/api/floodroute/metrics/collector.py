"""Pure-Python Prometheus metrics collector and registry for FloodRoute (TRD 13)."""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


def _escape_label_value(value: Any) -> str:
    """Escape a label value per the Prometheus exposition format."""
    return (
        str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )


def _format_labels(labels: dict[str, Any] | None) -> str:
    if not labels:
        return ""
    items = [f'{k}="{_escape_label_value(v)}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(items) + "}"


class Counter:
    """Thread-safe monotonic counter."""

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...] = ()):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._values: dict[tuple[Any, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, labels: dict[str, Any] | None = None) -> None:
        if amount < 0:
            raise ValueError("Counters can only be incremented monotonically.")
        key = tuple(labels.get(k, "") for k in self.label_names) if labels else ()
        with self._lock:
            self._values[key] += amount

    def get(self, labels: dict[str, Any] | None = None) -> float:
        key = tuple(labels.get(k, "") for k in self.label_names) if labels else ()
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0.0")
            for key, val in sorted(self._values.items()):
                label_dict = dict(zip(self.label_names, key)) if self.label_names else None
                lines.append(f"{self.name}{_format_labels(label_dict)} {val}")
        return lines


class Gauge:
    """Thread-safe variable gauge."""

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...] = ()):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._values: dict[tuple[Any, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, labels: dict[str, Any] | None = None) -> None:
        key = tuple(labels.get(k, "") for k in self.label_names) if labels else ()
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, labels: dict[str, Any] | None = None) -> None:
        key = tuple(labels.get(k, "") for k in self.label_names) if labels else ()
        with self._lock:
            self._values[key] += amount

    def dec(self, amount: float = 1.0, labels: dict[str, Any] | None = None) -> None:
        key = tuple(labels.get(k, "") for k in self.label_names) if labels else ()
        with self._lock:
            self._values[key] -= amount

    def get(self, labels: dict[str, Any] | None = None) -> float:
        key = tuple(labels.get(k, "") for k in self.label_names) if labels else ()
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} gauge"]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0.0")
            for key, val in sorted(self._values.items()):
                label_dict = dict(zip(self.label_names, key)) if self.label_names else None
                lines.append(f"{self.name}{_format_labels(label_dict)} {val}")
        return lines


class Histogram:
    """Thread-safe cumulative histogram for latency and distribution tracking."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: tuple[str, ...] = (),
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
    ):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.buckets = tuple(sorted(buckets))
        self._counts: dict[tuple[Any, ...], dict[float, int]] = defaultdict(
            lambda: {b: 0 for b in self.buckets}
        )
        self._sums: dict[tuple[Any, ...], float] = defaultdict(float)
        self._totals: dict[tuple[Any, ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: dict[str, Any] | None = None) -> None:
        key = tuple(labels.get(k, "") for k in self.label_names) if labels else ()
        with self._lock:
            self._totals[key] += 1
            self._sums[key] += value
            b_counts = self._counts[key]
            for b in self.buckets:
                if value <= b:
                    b_counts[b] += 1

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        with self._lock:
            all_keys = sorted(self._totals.keys())
            if not all_keys:
                lines.append(f"{self.name}_count 0")
                lines.append(f"{self.name}_sum 0.0")
            for key in all_keys:
                base_labels = dict(zip(self.label_names, key)) if self.label_names else {}
                b_counts = self._counts[key]
                cumulative = 0
                for b in self.buckets:
                    cumulative = b_counts[b]
                    lbls = {**base_labels, "le": str(b)}
                    lines.append(f"{self.name}_bucket{_format_labels(lbls)} {cumulative}")
                inf_lbls = {**base_labels, "le": "+Inf"}
                lines.append(f"{self.name}_bucket{_format_labels(inf_lbls)} {self._totals[key]}")
                lines.append(f"{self.name}_count{_format_labels(base_labels)} {self._totals[key]}")
                lines.append(f"{self.name}_sum{_format_labels(base_labels)} {self._sums[key]:.6f}")
        return lines


@dataclass
class FloodRouteMetrics:
    """Central metrics registry for FloodRoute SLOs and telemetry."""

    requests_total: Counter = field(
        default_factory=lambda: Counter(
            "floodroute_api_requests_total",
            "Total HTTP requests handled by endpoint and status.",
            ("endpoint", "method", "status"),
        )
    )
    request_duration_seconds: Histogram = field(
        default_factory=lambda: Histogram(
            "floodroute_api_request_duration_seconds",
            "HTTP request latency in seconds.",
            ("endpoint", "method"),
        )
    )
    adapter_lag_seconds: Gauge = field(
        default_factory=lambda: Gauge(
            "floodroute_adapter_lag_seconds",
            "Latency lag of external weather and alert data adapters.",
            ("source",),
        )
    )
    adapter_errors_total: Counter = field(
        default_factory=lambda: Counter(
            "floodroute_adapter_errors_total",
            "Total network and parsing failures for ingest adapters.",
            ("source",),
        )
    )
    score_runs_total: Counter = field(
        default_factory=lambda: Counter(
            "floodroute_score_runs_total",
            "Total scoring cycles executed.",
            ("status",),
        )
    )
    score_duration_seconds: Histogram = field(
        default_factory=lambda: Histogram(
            "floodroute_score_duration_seconds",
            "Execution duration of scoring pipeline runs in seconds.",
        )
    )
    segments_impassable_count: Gauge = field(
        default_factory=lambda: Gauge(
            "floodroute_segments_impassable_count",
            "Current count of active impassable road segments.",
            ("vclass", "city_id"),
        )
    )
    active_watches_count: Gauge = field(
        default_factory=lambda: Gauge(
            "floodroute_active_watches_count",
            "Current count of active citizen and fleet route watches.",
        )
    )
    webhook_deliveries_total: Counter = field(
        default_factory=lambda: Counter(
            "floodroute_webhook_deliveries_total",
            "Total enterprise webhook dispatch notifications.",
            ("status",),
        )
    )
    bot_alerts_total: Counter = field(
        default_factory=lambda: Counter(
            "floodroute_bot_alerts_total",
            "Total citizen alerts dispatched via WhatsApp and SMS channels.",
            ("channel", "status"),
        )
    )

    def render(self) -> str:
        """Render all registered metrics in standard Prometheus exposition format."""
        all_lines: list[str] = []
        for obj in [
            self.requests_total,
            self.request_duration_seconds,
            self.adapter_lag_seconds,
            self.adapter_errors_total,
            self.score_runs_total,
            self.score_duration_seconds,
            self.segments_impassable_count,
            self.active_watches_count,
            self.webhook_deliveries_total,
            self.bot_alerts_total,
        ]:
            all_lines.extend(obj.render())
        return "\n".join(all_lines) + "\n"


# Singleton instance
METRICS = FloodRouteMetrics()
