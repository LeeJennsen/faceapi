from collections import Counter as CounterStore
from threading import Lock
from time import perf_counter, time

from flask import Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

TOTAL_REQUESTS = Counter(
    "faceapi_http_requests_total",
    "Total HTTP requests served by the Flask API.",
    ("method", "endpoint", "status"),
)
ERROR_REQUESTS = Counter(
    "faceapi_http_error_requests_total",
    "Total HTTP requests that returned 4xx or 5xx responses.",
    ("method", "endpoint", "status"),
)
REQUEST_LATENCY = Histogram(
    "faceapi_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ("method", "endpoint"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
REQUESTS_BY_ENDPOINT = Counter(
    "faceapi_http_requests_by_endpoint_total",
    "Total HTTP requests aggregated by endpoint.",
    ("method", "endpoint"),
)
REQUESTS_IN_PROGRESS = Gauge(
    "faceapi_http_requests_in_progress",
    "In-flight HTTP requests currently being handled.",
)
DEPENDENCY_HEALTH = Gauge(
    "faceapi_dependency_health",
    "Dependency health status where 1 is healthy and 0 is unhealthy.",
    ("dependency",),
)
APP_INFO = Gauge(
    "faceapi_build_info",
    "Static application metadata.",
    ("service", "version"),
)


class _MetricsState:
    def __init__(self):
        self._lock = Lock()
        self.reset()

    def reset(self, *, service: str = "faceapi2", version: str = "unknown") -> None:
        with self._lock:
            self.service = service
            self.version = version
            self.started_at = time()
            self.total_requests = 0
            self.error_requests = 0
            self.total_latency_seconds = 0.0
            self.latency_samples = 0
            self.requests_in_progress = 0
            self.requests_by_status = CounterStore()
            self.requests_by_endpoint = CounterStore()
            self.dependencies = {}

    def request_started(self) -> None:
        with self._lock:
            self.requests_in_progress += 1

    def request_finished(self) -> None:
        with self._lock:
            self.requests_in_progress = max(self.requests_in_progress - 1, 0)

    def record_request(self, *, endpoint: str, status_code: int, latency_seconds: float | None) -> None:
        with self._lock:
            self.total_requests += 1
            if status_code >= 400:
                self.error_requests += 1

            if latency_seconds is not None:
                self.total_latency_seconds += max(latency_seconds, 0.0)
                self.latency_samples += 1

            self.requests_by_status[str(status_code)] += 1
            self.requests_by_endpoint[endpoint] += 1

    def set_dependency_health(self, name: str, healthy: bool) -> None:
        with self._lock:
            self.dependencies[name] = healthy

    def snapshot(self) -> dict:
        with self._lock:
            total_requests = self.total_requests
            error_requests = self.error_requests
            average_latency_ms = (
                self.total_latency_seconds / self.latency_samples * 1000
                if self.latency_samples
                else 0.0
            )
            requests_by_status = [
                {"status": status, "requests": int(count)}
                for status, count in sorted(
                    self.requests_by_status.items(),
                    key=lambda item: (int(item[0]) if str(item[0]).isdigit() else item[0]),
                )
            ]
            top_endpoints = [
                {"endpoint": endpoint, "requests": int(count)}
                for endpoint, count in sorted(
                    self.requests_by_endpoint.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:6]
            ]
            dependencies = dict(self.dependencies)
            requests_in_progress = self.requests_in_progress
            uptime_seconds = max(time() - self.started_at, 0.0)
            service = self.service
            version = self.version

        summary = {
            "total_requests": int(total_requests),
            "error_requests": int(error_requests),
            "error_rate_percent": round(
                (error_requests / total_requests * 100) if total_requests else 0.0,
                2,
            ),
            "average_latency_ms": round(average_latency_ms, 2),
            "requests_in_progress": int(requests_in_progress),
            "uptime_seconds": round(uptime_seconds, 2),
        }
        return {
            "service": service,
            "version": version,
            "total_requests": summary["total_requests"],
            "error_requests": summary["error_requests"],
            "error_rate_percent": summary["error_rate_percent"],
            "average_latency_ms": summary["average_latency_ms"],
            "summary": summary,
            "requests_by_status": requests_by_status,
            "top_endpoints": top_endpoints,
            "dependencies": dependencies,
        }


METRICS_STATE = _MetricsState()


def _endpoint_label() -> str:
    if request.url_rule and request.url_rule.rule:
        return request.url_rule.rule
    if request.path:
        return request.path
    if request.endpoint:
        return request.endpoint
    return "unknown"


def _finalize_request(status_code: int | None = None) -> None:
    if getattr(g, "_metrics_recorded", False):
        return

    endpoint = getattr(g, "_metrics_endpoint", _endpoint_label())
    method = request.method
    resolved_status_code = int(status_code or 500)
    latency_seconds = None
    start_time = getattr(g, "_metrics_start_time", None)
    if start_time is not None:
        latency_seconds = perf_counter() - start_time

    TOTAL_REQUESTS.labels(
        method=method,
        endpoint=endpoint,
        status=str(resolved_status_code),
    ).inc()
    REQUESTS_BY_ENDPOINT.labels(method=method, endpoint=endpoint).inc()

    if resolved_status_code >= 400:
        ERROR_REQUESTS.labels(
            method=method,
            endpoint=endpoint,
            status=str(resolved_status_code),
        ).inc()

    if latency_seconds is not None:
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency_seconds)

    METRICS_STATE.record_request(
        endpoint=endpoint,
        status_code=resolved_status_code,
        latency_seconds=latency_seconds,
    )

    if getattr(g, "_metrics_in_progress", False):
        REQUESTS_IN_PROGRESS.dec()
        METRICS_STATE.request_finished()
        g._metrics_in_progress = False

    g._metrics_recorded = True


def init_metrics(app):
    if app.extensions.get("prometheus_metrics_initialized"):
        return

    METRICS_STATE.reset(
        service=app.config.get("APP_NAME", "faceapi2"),
        version=app.config.get("API_VERSION", "unknown"),
    )
    APP_INFO.labels(
        service=app.config.get("APP_NAME", "faceapi2"),
        version=app.config.get("API_VERSION", "unknown"),
    ).set(1)

    @app.before_request
    def _before_request():
        g._metrics_start_time = perf_counter()
        g._metrics_endpoint = _endpoint_label()
        g._metrics_recorded = False
        g._metrics_in_progress = True
        REQUESTS_IN_PROGRESS.inc()
        METRICS_STATE.request_started()

    @app.after_request
    def _after_request(response):
        _finalize_request(response.status_code)
        return response

    @app.teardown_request
    def _teardown_request(exception):
        if exception is not None:
            _finalize_request(500)
        elif getattr(g, "_metrics_in_progress", False):
            REQUESTS_IN_PROGRESS.dec()
            METRICS_STATE.request_finished()
            g._metrics_in_progress = False

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    app.extensions["prometheus_metrics_initialized"] = True


def set_dependency_health(name: str, healthy: bool) -> None:
    DEPENDENCY_HEALTH.labels(dependency=name).set(1 if healthy else 0)
    METRICS_STATE.set_dependency_health(name, healthy)


def collect_metrics_snapshot() -> dict:
    return METRICS_STATE.snapshot()
