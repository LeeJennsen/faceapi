import app as app_module


def test_dashboard_route_renders(client):
    response = client.get("/v1/dashboard")

    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_dashboard_operations_tab_renders(client):
    response = client.get("/v1/dashboard?tab=operations")

    assert response.status_code == 200
    assert b"Operations" in response.data


def test_operations_route_redirects_to_dashboard_tab(client):
    response = client.get("/v1/dashboard/operations")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/v1/dashboard?tab=operations")


def test_legacy_operations_route_redirects(client):
    response = client.get("/v1/operations")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/v1/dashboard?tab=operations")


def test_metrics_endpoint_exposes_prometheus_payload(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"faceapi_http_requests_total" in response.data
    assert b"faceapi_http_error_requests_total" in response.data
    assert b"faceapi_http_requests_by_endpoint_total" in response.data


def test_health_ready_reports_upstream_status(client, monkeypatch):
    client.application.config["ENABLE_DEPENDENCY_CHECKS"] = True
    monkeypatch.setattr(app_module, "check_mysql_connection", lambda: (True, None))
    monkeypatch.setattr(app_module, "check_mongo_connection", lambda: (True, None))
    monkeypatch.setattr(app_module, "check_redis_connection", lambda: (True, None))

    response = client.get("/health/ready")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ready"] is True
    assert payload["dependencies"]["redis"]["status"] == "up"


def test_health_returns_503_when_dependency_is_down(client, monkeypatch):
    client.application.config["ENABLE_DEPENDENCY_CHECKS"] = True
    monkeypatch.setattr(app_module, "check_mysql_connection", lambda: (False, "connection failed"))
    monkeypatch.setattr(app_module, "check_mongo_connection", lambda: (True, None))
    monkeypatch.setattr(app_module, "check_redis_connection", lambda: (True, None))

    response = client.get("/health")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["dependencies"]["mysql"]["status"] == "down"


def test_operations_overview_returns_links_and_metrics(client, monkeypatch):
    client.application.config["ENABLE_DEPENDENCY_CHECKS"] = True
    monkeypatch.setattr(app_module, "check_mysql_connection", lambda: (True, None))
    monkeypatch.setattr(app_module, "check_mongo_connection", lambda: (True, None))
    monkeypatch.setattr(app_module, "check_redis_connection", lambda: (True, None))
    monkeypatch.setattr(app_module.Config, "GRAFANA_PUBLIC_URL", "http://grafana:3000")
    monkeypatch.setattr(app_module.Config, "PROMETHEUS_PUBLIC_URL", "http://prometheus:9090")
    monkeypatch.setattr(app_module.Config, "ALERTMANAGER_PUBLIC_URL", "http://alertmanager:9093")
    monkeypatch.setattr(app_module.Config, "LOKI_PUBLIC_URL", "http://loki:3100")

    response = client.get("/api/v1/ops/overview")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["health"]["status"] == "ok"
    assert payload["links"]["grafana"] == "http://localhost:3000"
    assert payload["links"]["prometheus"] == "http://localhost:9090"
    assert payload["links"]["alertmanager"] == "http://localhost:9093/#/alerts"
    assert payload["links"]["loki"] == "http://localhost:3100"
    assert "summary" in payload["metrics"]


def test_operations_overview_returns_live_request_metrics(client):
    client.get("/health/live")
    client.get("/health/live")
    client.get("/missing-route")

    response = client.get("/api/v1/ops/overview")

    assert response.status_code == 200
    payload = response.get_json()
    metrics = payload["metrics"]

    assert metrics["total_requests"] == 3
    assert metrics["summary"]["total_requests"] == 3
    assert metrics["error_requests"] == 1
    assert metrics["error_rate_percent"] == 33.33
    assert metrics["average_latency_ms"] >= 0
    assert {"status": "200", "requests": 2} in metrics["requests_by_status"]
    assert {"status": "404", "requests": 1} in metrics["requests_by_status"]
    assert metrics["top_endpoints"][0]["endpoint"] == "/health/live"
    assert metrics["top_endpoints"][0]["requests"] == 2
