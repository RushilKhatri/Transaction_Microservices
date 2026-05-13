"""
Prometheus metrics for the notification service.
"""

import os
import time

from flask import Response, g, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

HTTP_REQUESTS = Counter(
    "banking_http_requests",
    "Total HTTP requests handled by banking services.",
    ["banking_service", "method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "banking_http_request_duration_seconds",
    "HTTP request latency for banking services.",
    ["banking_service", "method", "endpoint"],
)


def _endpoint_label() -> str:
    if request.url_rule is not None:
        return request.url_rule.rule
    return request.endpoint or "unknown"


def _metrics_payload() -> bytes:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest(REGISTRY)


def register_metrics(app, service_name: str) -> None:
    @app.before_request
    def _start_metrics_timer():
        if request.path != "/metrics":
            g.prometheus_start_time = time.perf_counter()

    @app.after_request
    def _record_http_metrics(response):
        if request.path != "/metrics":
            duration = time.perf_counter() - getattr(g, "prometheus_start_time", time.perf_counter())
            endpoint = _endpoint_label()
            status = str(response.status_code)

            HTTP_REQUESTS.labels(service_name, request.method, endpoint, status).inc()
            HTTP_REQUEST_DURATION.labels(service_name, request.method, endpoint).observe(duration)
        return response

    @app.get("/metrics")
    def metrics():
        return Response(_metrics_payload(), content_type=CONTENT_TYPE_LATEST)
