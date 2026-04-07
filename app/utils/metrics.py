# Prometheus metrics using prometheus-client.

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from app.config import get_settings

registry = CollectorRegistry()
settings = get_settings()

LABELS = {"service": settings.service_name, "version": settings.service_version}

# ── HTTP Metrics ──────────────────────────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status_code"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route", "status_code"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
    registry=registry,
)

# ── Blockchain Business Metrics ───────────────────────────────────────────────

blocks_total = Gauge(
    "blockchain_blocks_total",
    "Total number of blocks in the chain",
    registry=registry,
)

blockchain_operations_total = Counter(
    "blockchain_operations_total",
    "Total blockchain operations",
    ["operation", "block_type", "status"],  # operation: add|validate|verify
    registry=registry,
)

chain_validation_duration_seconds = Histogram(
    "chain_validation_duration_seconds",
    "Time to validate the entire chain",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1],
    registry=registry,
)

chain_valid = Gauge(
    "blockchain_chain_valid",
    "1 if chain is valid, 0 if tampered",
    registry=registry,
)

# Set initial state
chain_valid.set(1)
blocks_total.set(1)  # genesis block


def get_metrics() -> tuple[bytes, str]:
    """Return Prometheus metrics in text format."""
    return generate_latest(registry), CONTENT_TYPE_LATEST